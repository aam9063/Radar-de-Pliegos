"""Deterministic GO/NO-GO/REVISAR decision engine (S6, RP-06).

Pure domain module: no FastAPI, SQLAlchemy or AI SDK imports, and it NEVER
calls the LLM. The LLM only rewrites the already-computed reasons into a
summary (S6: "no decide nada"); every verdict here is reproducible code.

Rules, in evaluation order (NO-GO wins over REVISAR whenever both apply —
every reason is collected and the result is the most severe level):

1. Required classification the company does not hold  → NO-GO.
2. Required economic solvency above the annual volume → NO-GO.
3. Days until the deadline below the profile minimum  → NO-GO.
4. Budget outside the profile's interest range        → REVISAR.
5. Any critical field null or unverified              → REVISAR.
6. Otherwise                                          → GO.

Every reason links to the evidencia of the field that causes it.
"""

import re
from collections.abc import Sequence
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from app.domain.perfil_empresa import ClasificacionEmpresa, PerfilEmpresa
from app.domain.pliego_ficha import (
    CampoExtraido,
    ClasificacionRequerida,
    Evidencia,
    PliegoFicha,
)


class Resultado(StrEnum):
    """Final verdict of the engine (most severe level of the collected reasons)."""

    GO = "GO"
    NO_GO = "NO-GO"
    REVISAR = "REVISAR"


class NivelRazon(StrEnum):
    """Severity of one reason: only NO-GO and REVISAR produce reasons."""

    NO_GO = "NO-GO"
    REVISAR = "REVISAR"


class Razon(BaseModel):
    """One reason, linked to the evidencia of the field that causes it."""

    campo: str
    nivel: NivelRazon
    descripcion: str
    evidencia: list[Evidencia] = []


class ResultadoDecision(BaseModel):
    """Engine output: the verdict plus every reason behind it."""

    resultado: Resultado
    razones: list[Razon] = []


#: Fields the decision depends on (plus minimal identification). A field here
#: that is null or unverified forces at least REVISAR (rule 5).
CAMPOS_CRITICOS: tuple[str, ...] = (
    "objeto",
    "presupuesto_base_sin_iva",
    "fecha_limite_presentacion",
    "clasificacion_exigida",
    "solvencia_economica",
)

#: Formats accepted for the free-text deadline (Spanish day-first and ISO).
_FORMATOS_FECHA: tuple[str, ...] = (
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
)

#: Numbers adjacent to a currency marker (€, EUR, euro, euros), before or after.
#: Solvencia_economica is free text (S3), so only currency-anchored numbers are
#: considered amounts; anything else would turn arbitrary figures into NO-GOs.
_PATRON_IMPORTE = re.compile(
    r"(\d[\d.,]*)\s*(?:€|euro?s?\b)|(?:(?:€|euro?s?\b)\s*(\d[\d.,]*))",
    re.IGNORECASE,
)


def _parsear_numero(texto: str) -> float | None:
    """Parse a Spanish-formatted number: dots as thousands, comma as decimal."""
    normalizado = texto.replace(".", "").replace(",", ".")
    try:
        return float(normalizado)
    except ValueError:
        return None


def maximo_importe_euros(textos: Sequence[str]) -> float | None:
    """Largest currency-marked amount across the solvencia strings, or None.

    Deterministic helper for the free-text ``solvencia_economica`` field: it
    keeps only numbers next to a currency marker and parses them with Spanish
    conventions. ``None`` means "cannot quantify" and yields REVISAR, never
    NO-GO.
    """
    importes = [
        parseado
        for texto in textos
        for coincidencia in _PATRON_IMPORTE.finditer(texto)
        for crudo in coincidencia.groups()
        if crudo is not None and (parseado := _parsear_numero(crudo)) is not None
    ]
    return max(importes) if importes else None


def interpretar_fecha(texto: str) -> date | None:
    """Interpret the free-text deadline, or None when it cannot be parsed."""
    limpio = texto.strip()
    for formato in _FORMATOS_FECHA:
        try:
            return datetime.strptime(limpio, formato).date()
        except ValueError:
            continue
    return None


def _normalizar_codigo(valor: str) -> str:
    """Lowercase, trimmed code without leading zeros ('01' == '1')."""
    sin_ceros = valor.strip().lower().lstrip("0")
    return sin_ceros if sin_ceros else "0"


def _categoria_normalizada(valor: str) -> str:
    return valor.strip().lower()


def empresa_cubre_clasificacion(
    requerida: ClasificacionRequerida, propias: Sequence[ClasificacionEmpresa]
) -> bool:
    """Whether the company holds at least the required classification.

    Grupo and subgrupo must match exactly (normalized). Categories are letters
    where ``a < b < c``: the company qualifies when its category is equal or
    higher. A requirement without category needs only the matching
    grupo/subgrupo; a company without category never proves a required one.
    """
    for propia in propias:
        if _normalizar_codigo(propia.grupo) != _normalizar_codigo(requerida.grupo):
            continue
        if _normalizar_codigo(propia.subgrupo) != _normalizar_codigo(requerida.subgrupo):
            continue
        if requerida.categoria is None:
            return True
        if propia.categoria is None:
            return False
        return _categoria_normalizada(propia.categoria) >= _categoria_normalizada(
            requerida.categoria
        )
    return False


def _campos_criticos(ficha: PliegoFicha) -> list[tuple[str, CampoExtraido[Any]]]:
    """Critical fields in stable order, for the rule-5 scan."""
    return [
        ("objeto", ficha.objeto),
        ("presupuesto_base_sin_iva", ficha.presupuesto_base_sin_iva),
        ("fecha_limite_presentacion", ficha.fecha_limite_presentacion),
        ("clasificacion_exigida", ficha.clasificacion_exigida),
        ("solvencia_economica", ficha.solvencia_economica),
    ]


def _etiqueta_clasificacion(requerida: ClasificacionRequerida) -> str:
    etiqueta = f"{requerida.grupo}.{requerida.subgrupo}"
    if requerida.categoria:
        etiqueta += f".{requerida.categoria}"
    return etiqueta


def evaluar(ficha: PliegoFicha, perfil: PerfilEmpresa, *, hoy: date) -> ResultadoDecision:
    """Run the deterministic decision rules (S6). Never calls the LLM."""
    razones: list[Razon] = []

    # Rule 1 — required classification covered by the company.
    exigidas = ficha.clasificacion_exigida.valor or []
    if not exigidas:
        razones.append(
            Razon(
                campo="clasificacion_exigida",
                nivel=NivelRazon.NO_GO,
                descripcion=(
                    "La ficha no registra ninguna clasificación exigida (campo vacío o ausente)."
                ),
                evidencia=list(ficha.clasificacion_exigida.evidencia),
            )
        )
    else:
        for requerida in exigidas:
            if not empresa_cubre_clasificacion(requerida, perfil.clasificaciones):
                razones.append(
                    Razon(
                        campo="clasificacion_exigida",
                        nivel=NivelRazon.NO_GO,
                        descripcion=(
                            "La empresa no acredita la clasificación exigida "
                            f"{_etiqueta_clasificacion(requerida)}."
                        ),
                        evidencia=list(ficha.clasificacion_exigida.evidencia),
                    )
                )

    # Rule 2 — required economic solvency vs the company's annual volume.
    solvencias = ficha.solvencia_economica.valor or []
    if solvencias:
        importe = maximo_importe_euros(solvencias)
        if importe is None:
            razones.append(
                Razon(
                    campo="solvencia_economica",
                    nivel=NivelRazon.REVISAR,
                    descripcion=(
                        "La solvencia económica exigida no incluye ningún importe con divisa; "
                        "no se puede comparar con el volumen anual de la empresa."
                    ),
                    evidencia=list(ficha.solvencia_economica.evidencia),
                )
            )
        elif importe > perfil.volumen_anual:
            razones.append(
                Razon(
                    campo="solvencia_economica",
                    nivel=NivelRazon.NO_GO,
                    descripcion=(
                        f"La solvencia económica exigida ({importe:.2f} EUR) supera el "
                        f"volumen anual de la empresa ({perfil.volumen_anual:.2f} EUR)."
                    ),
                    evidencia=list(ficha.solvencia_economica.evidencia),
                )
            )

    # Rule 3 — days until the deadline vs the profile minimum.
    fecha_texto = ficha.fecha_limite_presentacion.valor
    if fecha_texto is not None:
        fecha_limite = interpretar_fecha(fecha_texto)
        if fecha_limite is None:
            razones.append(
                Razon(
                    campo="fecha_limite_presentacion",
                    nivel=NivelRazon.REVISAR,
                    descripcion=(
                        f"No se ha podido interpretar la fecha límite de presentación "
                        f"('{fecha_texto}')."
                    ),
                    evidencia=list(ficha.fecha_limite_presentacion.evidencia),
                )
            )
        else:
            dias = (fecha_limite - hoy).days
            if dias < perfil.dias_minimos:
                razones.append(
                    Razon(
                        campo="fecha_limite_presentacion",
                        nivel=NivelRazon.NO_GO,
                        descripcion=(
                            f"Quedan {dias} días hasta la fecha límite de presentación y el "
                            f"perfil exige un mínimo de {perfil.dias_minimos} días para "
                            "preparar la oferta."
                        ),
                        evidencia=list(ficha.fecha_limite_presentacion.evidencia),
                    )
                )

    # Rule 4 — budget inside the profile's interest range.
    presupuesto = ficha.presupuesto_base_sin_iva.valor
    if presupuesto is not None:
        rango = perfil.rango_presupuesto
        if presupuesto < rango.min:
            razones.append(
                Razon(
                    campo="presupuesto_base_sin_iva",
                    nivel=NivelRazon.REVISAR,
                    descripcion=(
                        f"El presupuesto base sin IVA ({presupuesto:.2f} EUR) está por debajo "
                        f"del rango de interés de la empresa "
                        f"([{rango.min:.2f}, {rango.max:.2f}] EUR)."
                    ),
                    evidencia=list(ficha.presupuesto_base_sin_iva.evidencia),
                )
            )
        elif presupuesto > rango.max:
            razones.append(
                Razon(
                    campo="presupuesto_base_sin_iva",
                    nivel=NivelRazon.REVISAR,
                    descripcion=(
                        f"El presupuesto base sin IVA ({presupuesto:.2f} EUR) está por encima "
                        f"del rango de interés de la empresa "
                        f"([{rango.min:.2f}, {rango.max:.2f}] EUR)."
                    ),
                    evidencia=list(ficha.presupuesto_base_sin_iva.evidencia),
                )
            )

    # Rule 5 — any critical field null or unverified forces at least REVISAR.
    for nombre, campo in _campos_criticos(ficha):
        if campo.valor is None:
            razones.append(
                Razon(
                    campo=nombre,
                    nivel=NivelRazon.REVISAR,
                    descripcion=f"El campo crítico '{nombre}' está sin valor en la ficha.",
                    evidencia=list(campo.evidencia),
                )
            )
        elif not campo.verificado:
            razones.append(
                Razon(
                    campo=nombre,
                    nivel=NivelRazon.REVISAR,
                    descripcion=f"El campo crítico '{nombre}' no tiene sus evidencias verificadas.",
                    evidencia=list(campo.evidencia),
                )
            )

    if any(razon.nivel is NivelRazon.NO_GO for razon in razones):
        resultado = Resultado.NO_GO
    elif razones:
        resultado = Resultado.REVISAR
    else:
        resultado = Resultado.GO
    return ResultadoDecision(resultado=resultado, razones=razones)
