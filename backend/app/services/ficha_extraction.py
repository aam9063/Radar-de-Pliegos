"""Structured extraction of ``PliegoFicha`` from licitación pages (S3, RP-04/RP-05).

Orchestration lives here (services layer): the licitación's documents are
extracted one by one (BRIEF §7: "se envía documento a documento y se fusionan
resultados"), each document's prompt is built from only its own pages with
``[[DOC:<tipo>|P:<número>]]`` markers, the LLM is reached through the
``LLMClient`` port, and each answer is validated against ``PliegoFicha`` with a
single retry. The per-document results are then fused deterministically by
source priority and their evidence is verified against the stored pages before
anything is persisted.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.models import Documento, Ficha, Licitacion
from app.domain.fusion_ficha import SOURCE_PRIORITY, FichaFuente, fusionar_fichas
from app.domain.llm import LLMClient, LLMInvalidJSONError
from app.domain.pliego_ficha import ExtractionInvalidOutputError, PliegoFicha
from app.domain.verificacion_ficha import verificar_ficha

PLIEGO_FICHA_SCHEMA: dict[str, Any] = PliegoFicha.model_json_schema()

_PROMPT_HEADER = """\
Eres un extractor de datos de pliegos de contratación pública española.
Extrae los datos solicitados del texto siguiente y responde SOLO con un objeto
JSON válido conforme al esquema ``PliegoFicha`` incluido al final.

Reglas:
- Cada campo es un objeto con "valor", "evidencia" y "confianza".
- Si el dato NO aparece en el texto, usa "valor": null y "evidencia": [].
  Nunca inventes ni deduzcas datos que no estén literalmente en el texto.
- Cada evidencia usa el documento y la página marcados en el texto con
  [[DOC:<tipo>|P:<número>]], y la cita es un fragmento literal de esa página de
  30 palabras como máximo.
- "confianza" es "alta", "media" o "baja" según lo explícito del dato.
"""

_RETRY_INSTRUCTIONS = """\
La respuesta anterior no pasó la validación del esquema. Error de validación:
{error}

Corrige el problema y responde de nuevo SOLO con el objeto JSON válido.
"""


@dataclass(frozen=True)
class PageText:
    """One pliego page as prompt input, decoupled from ORM models."""

    documento: str
    numero: int
    texto: str


def build_prompt(pages: Sequence[PageText]) -> str:
    """Build the extraction prompt: marked pages ordered by source priority."""
    ordered = sorted(
        pages,
        key=lambda page: (
            SOURCE_PRIORITY.get(page.documento, len(SOURCE_PRIORITY)),
            page.documento,
            page.numero,
        ),
    )
    blocks = [
        f"[[DOC:{page.documento}|P:{page.numero}]]\n{page.texto}"
        for page in ordered
        if page.texto.strip()
    ]
    body = "\n\n".join(blocks) if blocks else "(sin texto de pliego)"
    return f"{_PROMPT_HEADER}\n\n{body}\n\nEsquema PliegoFicha:\n{json.dumps(PLIEGO_FICHA_SCHEMA)}"


def _retry_prompt(prompt: str, error: Exception) -> str:
    """Append the validation failure so the model can fix its answer."""
    return f"{prompt}\n\n{_RETRY_INSTRUCTIONS.format(error=error)}"


class PliegoExtractor:
    """Validated ``PliegoFicha`` extraction with one retry on invalid output.

    Retries (exactly once) when the answer fails ``PliegoFicha`` validation or
    is not parseable JSON, sending the validation error back to the model. A
    second failure raises ``ExtractionInvalidOutputError``; provider faults
    (rate limit, server errors) propagate untouched.
    """

    def __init__(self, llm_client: LLMClient, model: str) -> None:
        self._llm_client = llm_client
        self._model = model

    async def extract(self, prompt: str) -> PliegoFicha:
        try:
            return await self._ask_and_validate(prompt)
        except (ValidationError, LLMInvalidJSONError) as first_error:
            try:
                return await self._ask_and_validate(_retry_prompt(prompt, first_error))
            except (ValidationError, LLMInvalidJSONError) as second_error:
                raise ExtractionInvalidOutputError(
                    "La extracción del pliego falló: la respuesta del modelo no "
                    "valida contra PliegoFicha ni tras el reintento."
                ) from second_error

    async def _ask_and_validate(self, prompt: str) -> PliegoFicha:
        answer = await self._llm_client.complete_json(
            model=self._model, prompt=prompt, schema=PLIEGO_FICHA_SCHEMA
        )
        return PliegoFicha.model_validate(answer)


def _pages_from_documento(documento: Documento) -> tuple[list[PageText], int]:
    """Collect one document's page texts (skipping pages without text) and count those."""
    pages: list[PageText] = []
    skipped = 0
    for pagina in documento.paginas:
        if pagina.sin_texto or not pagina.texto.strip():
            skipped += 1
            continue
        pages.append(
            PageText(documento=documento.tipo.value, numero=pagina.numero, texto=pagina.texto)
        )
    return pages, skipped


def _paginas_por_tipo(documentos: Sequence[Documento]) -> dict[str, dict[int, str]]:
    """Map document type → page number → page text, for evidence verification."""
    paginas: dict[str, dict[int, str]] = {}
    for documento in documentos:
        por_tipo = paginas.setdefault(documento.tipo.value, {})
        for pagina in documento.paginas:
            por_tipo[pagina.numero] = pagina.texto
    return paginas


def _documentos_ordenados(documentos: Sequence[Documento]) -> list[Documento]:
    """Order documents by source priority (then id) so LLM calls are deterministic."""
    return sorted(
        documentos,
        key=lambda documento: (
            SOURCE_PRIORITY.get(documento.tipo.value, len(SOURCE_PRIORITY)),
            documento.id,
        ),
    )


async def extract_ficha_for_licitacion(
    session: AsyncSession,
    licitacion: Licitacion,
    llm_client: LLMClient,
    settings: Settings,
) -> Ficha:
    """Extract, fuse and verify the dossier of ``licitacion`` and persist it.

    Each document is extracted separately (one prompt per document, one retry
    on invalid output). If ANY document's extraction fails even after its
    retry, the typed error propagates and nothing is persisted. Otherwise the
    per-document results are fused by source priority, their evidence is
    verified against the stored pages, and the fused dossier replaces any
    existing ``Ficha`` row (one dossier per licitación).
    """
    documentos = (
        await session.scalars(
            select(Documento)
            .where(Documento.licitacion_id == licitacion.id)
            .options(selectinload(Documento.paginas))
        )
    ).all()

    extractor = PliegoExtractor(llm_client, settings.extraction_model)
    fuentes: list[FichaFuente] = []
    sin_texto = 0
    for documento in _documentos_ordenados(documentos):
        pages, skipped = _pages_from_documento(documento)
        sin_texto += skipped
        ficha_documento = await extractor.extract(build_prompt(pages))
        fuentes.append(FichaFuente(tipo=documento.tipo.value, ficha=ficha_documento))

    fusion = fusionar_fichas(fuentes)
    ficha = verificar_ficha(fusion.ficha, _paginas_por_tipo(documentos))

    avisos: list[str] = []
    if sin_texto:
        avisos.append(f"{sin_texto} páginas sin texto (escaneadas) se omitieron")
    avisos.extend(fusion.avisos)

    existing = await session.scalar(select(Ficha).where(Ficha.licitacion_id == licitacion.id))
    if existing is not None:
        existing.datos = ficha.model_dump(mode="json")
        existing.modelo = settings.extraction_model
        existing.avisos = avisos
        await session.commit()
        return existing

    row = Ficha(
        licitacion_id=licitacion.id,
        datos=ficha.model_dump(mode="json"),
        modelo=settings.extraction_model,
        avisos=avisos,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
