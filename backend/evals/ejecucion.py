"""Extraction orchestration for the evaluation run (RP-08 / S8).

Reuses the REAL extraction pipeline of ``app.services.ficha_extraction`` at the
service level — per-document ``PliegoExtractor`` calls, deterministic fusion by
source priority and evidence verification — but reads the pliegos as PDF files
from the evaluation data directory instead of the database. The LLM client is
injected (the real ``NanLLMClient`` in the CLI, ``FakeLLMClient`` in tests), so
no test ever reaches the real API.
"""

from collections.abc import Sequence
from pathlib import Path

from app.domain.fusion_ficha import SOURCE_PRIORITY, FichaFuente, fusionar_fichas
from app.domain.llm import LLMClient
from app.domain.pliego_ficha import PliegoFicha
from app.domain.verificacion_ficha import verificar_ficha
from app.services.ficha_extraction import PageText, PliegoExtractor, build_prompt
from app.services.page_extraction import extract_pages
from evals.ground_truth import DocumentoPliego


def _prioridad(documento: DocumentoPliego) -> int:
    return SOURCE_PRIORITY.get(documento.tipo, len(SOURCE_PRIORITY))


async def extraer_ficha_de_pdfs(
    documentos: Sequence[DocumentoPliego], dir_pliegos: Path, llm: LLMClient, model: str
) -> PliegoFicha:
    """Extract, fuse and verify the dossier of one annotated pliego.

    Documents are processed in source-priority order (one LLM call per PDF,
    with its own retry on invalid output). A missing PDF file raises
    ``FileNotFoundError`` naming the file.
    """
    extractor = PliegoExtractor(llm, model)
    fuentes: list[FichaFuente] = []
    paginas_por_tipo: dict[str, dict[int, str]] = {}

    for documento in sorted(documentos, key=lambda d: (_prioridad(d), d.archivo)):
        ruta = dir_pliegos / documento.archivo
        if not ruta.is_file():
            raise FileNotFoundError(f"el pliego '{documento.archivo}' no existe en {dir_pliegos}")
        paginas = extract_pages(ruta.read_bytes())
        por_tipo = paginas_por_tipo.setdefault(documento.tipo, {})
        page_texts = [
            PageText(documento=documento.tipo, numero=pagina.numero, texto=pagina.texto)
            for pagina in paginas
        ]
        por_tipo.update({pagina.numero: pagina.texto for pagina in paginas})
        ficha_documento = await extractor.extract(build_prompt(page_texts))
        fuentes.append(FichaFuente(tipo=documento.tipo, ficha=ficha_documento))

    fusion = fusionar_fichas(fuentes)
    return verificar_ficha(fusion.ficha, paginas_por_tipo)
