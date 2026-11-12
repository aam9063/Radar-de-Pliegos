"""Deterministic evidence verification for ``PliegoFicha`` (S4, RP-05 / AC-05).

Pure domain rule: for each evidence, check that the literal citation appears
in the text of the cited page. The match is normalized (lowercase, collapsed
whitespace, accents stripped) with a fuzzy tolerance of ``>= 0.9`` via
``rapidfuzz.fuzz.partial_ratio``. A field with any unverifiable evidence
becomes ``verificado = False``; its value and evidence are kept untouched.

No FastAPI, SQLAlchemy or AI SDK imports (architecture rule, AGENTS.md §8).
"""

import unicodedata
from collections.abc import Mapping

from rapidfuzz.fuzz import partial_ratio

from app.domain.pliego_ficha import Evidencia, PliegoFicha

# BRIEF S4: normalized fuzzy tolerance >= 0.9 (partial_ratio is scored 0-100).
FUZZY_THRESHOLD = 0.9


def normalizar_texto(texto: str) -> str:
    """Lowercase, strip accents and collapse whitespace for fuzzy matching."""
    sin_acentos = "".join(
        character
        for character in unicodedata.normalize("NFD", texto.casefold())
        if unicodedata.category(character) != "Mn"
    )
    return " ".join(sin_acentos.split())


def _cita_en_pagina(evidencia: Evidencia, paginas: Mapping[str, Mapping[int, str]]) -> bool:
    texto = paginas.get(evidencia.documento, {}).get(evidencia.pagina)
    if texto is None:
        return False
    ratio = partial_ratio(normalizar_texto(evidencia.cita), normalizar_texto(texto))
    return ratio / 100 >= FUZZY_THRESHOLD


def verificar_ficha(ficha: PliegoFicha, paginas: Mapping[str, Mapping[int, str]]) -> PliegoFicha:
    """Return a copy of ``ficha`` with ``verificado`` set per field evidence.

    ``paginas`` maps document type → page number → page text. Evidence pointing
    to a page that is unknown (missing type, missing page, or a scanned page
    without text) can never be matched and marks the field unverified.
    """
    campos: dict[str, dict[str, object]] = {}
    for name in PliegoFicha.model_fields:
        campo = getattr(ficha, name)
        if campo.evidencia and not all(_cita_en_pagina(ev, paginas) for ev in campo.evidencia):
            campo = campo.model_copy(update={"verificado": False})
        campos[name] = campo.model_dump()
    return PliegoFicha.model_validate(campos)
