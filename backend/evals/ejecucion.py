"""Extraction orchestration for the evaluation run (RP-08 / S8).

Reuses the REAL extraction pipeline of ``app.services.ficha_extraction`` at the
service level — per-document ``PliegoExtractor`` calls, deterministic fusion by
source priority and evidence verification — but reads the pliegos as PDF files
from the evaluation data directory instead of the database. The LLM client is
injected (the real ``NanLLMClient`` in the CLI, ``FakeLLMClient`` in tests), so
no test ever reaches the real API.

It also applies the deterministic subcontratación fallback (S2, MP-01,
``feat/mejorar-precision``): when the fused/verified dossier still has
``subcontratacion_limites.valor is None``, the real page texts are scanned for
the clause (analysis: EXP5/Ronda returned null although the clause is in
cláusula 30) and the field is filled without LLM involvement.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.domain.fusion_ficha import SOURCE_PRIORITY, FichaFuente, fusionar_fichas
from app.domain.llm import LLMClient
from app.domain.pliego_ficha import Confianza, Evidencia, PliegoFicha
from app.domain.verificacion_ficha import normalizar_texto, verificar_ficha
from app.services.ficha_extraction import PageText, PliegoExtractor, build_prompt
from app.services.page_extraction import extract_pages
from evals.ground_truth import DocumentoPliego

# Characters of normalized text scanned on each side of every "subcontrat"
# occurrence when looking for the limit of the clause.
_VENTANA_SUBCONTRATACION = 400
_FRASE_SIN_LIMITE = "Sin límite porcentual específico"
_SUFIJO_ARTICULO_215 = " conforme al artículo 215 de la LCSP"
# "... hasta un 50 % del contrato del precio de adjudicación ..."
_RE_PCT_CONTRATO = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*%\s*(?:del\s+|de\s+)(?:precio\s+de\s+adjudicacion\s+)?contrato"
)
# "Límite (%): 50" / "límite máximo de subcontratación: 30%" (Anexo I, epígrafe 15).
_RE_LIMITE_PCT = re.compile(
    r"limite\s*(?:\(\s*%\s*\)|maximo|maxima)?\s*[:\-]\s*(\d+(?:[.,]\d+)?)\s*%?"
)


def _prioridad(documento: DocumentoPliego) -> int:
    return SOURCE_PRIORITY.get(documento.tipo, len(SOURCE_PRIORITY))


@dataclass(frozen=True)
class _ClausulaSubcontratacion:
    """Deterministic fallback finding: value, evidence at hand and verbatim cita."""

    valor: str
    cita: str
    documento: str
    pagina: int


def _cita_literal_de_pagina(texto: str) -> str:
    """Verbatim cita (≤ 30 words) in ``texto`` starting at the clause mention.

    The citation is honest by construction: it is a literal fragment of the
    very page stored in ``evidencia``, so the deterministic verification pass
    can match it.
    """
    mencion = re.search(r"subcontrat", texto, re.IGNORECASE)
    inicio = mencion.start() if mencion else 0
    return " ".join(texto[inicio:].split()[:30])


def _hallazgo_en_pagina(texto: str) -> tuple[str, str] | None:
    """Extract (valor, cita) for one page whose normalized text mentions
    "subcontrat", scanning windows around each occurrence. Returns ``None``
    when no limit pattern is found in any window (the caller keeps scanning
    further pages).

    Rule order per window: an explicit "sin límite" phrase wins (plus the
    art. 215 mention when present); then a percentage tied to the contract or
    a "Límite (%): N" label; then a bare reference to "artículo 215" (the
    clause only defers to the legal regime).
    """
    normalizado = normalizar_texto(texto)
    ventanas = [
        normalizado[
            max(0, m.start() - _VENTANA_SUBCONTRATACION) : m.end() + _VENTANA_SUBCONTRATACION
        ]
        for m in re.finditer("subcontrat", normalizado)
    ]
    for ventana in ventanas:
        if "sin limite" in ventana:
            valor = _FRASE_SIN_LIMITE
            if "articulo 215" in ventana:
                valor += _SUFIJO_ARTICULO_215
            return valor, _cita_literal_de_pagina(texto)
    for ventana in ventanas:
        coincidencia = _RE_PCT_CONTRATO.search(ventana) or _RE_LIMITE_PCT.search(ventana)
        if coincidencia:
            porcentaje = coincidencia.group(1).replace(",", ".")
            return (
                f"Se permite subcontratar hasta el {porcentaje}% del contrato",
                _cita_literal_de_pagina(texto),
            )
    for ventana in ventanas:
        # Cláusula que solo remite al artículo 215 (EXP1/EXP3, análisis): sin
        # porcentaje y sin frase de “sin límite” en el propio documento.
        if "articulo 215" in ventana:
            return (
                "Se permite subcontratar conforme al artículo 215 de la LCSP",
                _cita_literal_de_pagina(texto),
            )
    return None


def _buscar_clausula_subcontratacion(
    paginas_por_tipo: Mapping[str, Mapping[int, str]],
) -> _ClausulaSubcontratacion | None:
    """Scan the pliego pages (source priority, then page number) for the
    subcontratación clause and its limit.

    Deterministic rules, in order inside every window around a "subcontrat"
    mention: an explicit "sin límite" phrase wins (plus the art. 215 mention
    when present); otherwise a percentage tied to the contract or a "Límite
    (%): N" label. No LLM is involved.
    """
    for tipo in sorted(
        paginas_por_tipo, key=lambda t: SOURCE_PRIORITY.get(t, len(SOURCE_PRIORITY))
    ):
        for numero in sorted(paginas_por_tipo[tipo]):
            texto = paginas_por_tipo[tipo][numero]
            if "subcontrat" not in normalizar_texto(texto):
                continue
            hallazgo = _hallazgo_en_pagina(texto)
            if hallazgo is not None:
                valor, cita = hallazgo
                return _ClausulaSubcontratacion(valor, cita, tipo, numero)
    return None


def _fallback_subcontratacion(
    ficha: PliegoFicha, paginas_por_tipo: Mapping[str, Mapping[int, str]]
) -> PliegoFicha:
    """S2 (MP-01): deterministic fallback when the LLM leaves subcontratación null.

    Documented choice: the field is filled from the real page text with REAL
    evidence (the document type, the page and a verbatim ≤ 30-word cita of the
    clause), ``confianza = "media"`` because the value is rule-extracted rather
    than model-extracted, and the verification pass is re-run so ``verificado``
    stays honest. When no clause/limit is found the field stays ``null`` with
    empty evidence — nothing is invented.
    """
    if ficha.subcontratacion_limites.valor is not None:
        return ficha
    hallazgo = _buscar_clausula_subcontratacion(paginas_por_tipo)
    if hallazgo is None:
        return ficha
    campo = ficha.subcontratacion_limites.model_copy(
        update={
            "valor": hallazgo.valor,
            "evidencia": [
                Evidencia(
                    documento=hallazgo.documento,
                    pagina=hallazgo.pagina,
                    cita=hallazgo.cita,
                )
            ],
            "confianza": Confianza.MEDIA,
        }
    )
    actualizada = ficha.model_copy(update={"subcontratacion_limites": campo})
    return verificar_ficha(actualizada, paginas_por_tipo)


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
    ficha_verificada = verificar_ficha(fusion.ficha, paginas_por_tipo)
    return _fallback_subcontratacion(ficha_verificada, paginas_por_tipo)
