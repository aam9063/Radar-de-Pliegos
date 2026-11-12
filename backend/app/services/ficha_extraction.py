"""Structured extraction of ``PliegoFicha`` from licitación pages (S3, RP-04).

Orchestration lives here (services layer): the prompt is built from the
licitación's pages with ``[[DOC:<tipo>|P:<número>]]`` markers, the LLM is
reached through the ``LLMClient`` port, and the answer is validated against
``PliegoFicha`` with a single retry before raising the typed domain error.
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
from app.domain.llm import LLMClient, LLMInvalidJSONError
from app.domain.pliego_ficha import ExtractionInvalidOutputError, PliegoFicha

# BRIEF S3 source priority when sources conflict (RP-05 fuses with it).
_SOURCE_PRIORITY: dict[str, int] = {"PCAP": 0, "ANEXO": 1, "PPT": 2, "OTRO": 3}

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
            _SOURCE_PRIORITY.get(page.documento, len(_SOURCE_PRIORITY)),
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


def _pages_from_documentos(documentos: Sequence[Documento]) -> tuple[list[PageText], int]:
    """Collect page texts (skipping pages without text) and count those skipped."""
    pages: list[PageText] = []
    skipped = 0
    for documento in documentos:
        tipo = documento.tipo.value
        for pagina in documento.paginas:
            if pagina.sin_texto or not pagina.texto.strip():
                skipped += 1
                continue
            pages.append(PageText(documento=tipo, numero=pagina.numero, texto=pagina.texto))
    return pages, skipped


async def extract_ficha_for_licitacion(
    session: AsyncSession,
    licitacion: Licitacion,
    llm_client: LLMClient,
    settings: Settings,
) -> Ficha:
    """Extract the dossier of ``licitacion`` and persist it as a ``Ficha`` row.

    Nothing is persisted unless the extraction validates: the row is written
    only after ``PliegoFicha`` validation succeeds (possibly after one retry).
    An existing ficha is replaced so the table keeps one dossier per licitación.
    """
    documentos = (
        await session.scalars(
            select(Documento)
            .where(Documento.licitacion_id == licitacion.id)
            .options(selectinload(Documento.paginas))
        )
    ).all()
    pages, sin_texto = _pages_from_documentos(documentos)

    extractor = PliegoExtractor(llm_client, settings.extraction_model)
    ficha = await extractor.extract(build_prompt(pages))

    avisos: list[str] = []
    if sin_texto:
        avisos.append(f"{sin_texto} páginas sin texto (escaneadas) se omitieron")

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
