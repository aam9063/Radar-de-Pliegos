"""Deterministic comparison between a ground truth annotation and an extracted
``PliegoFicha`` (RP-08 / S8), plus the aggregated evaluation metrics.

Pure Python: no FastAPI, SQLAlchemy or AI SDK imports. Float comparisons use a
relative tolerance of 0.1 % for the economic fields; lists compare
order-insensitively (sorted canonical JSON) because the LLM is free to emit
elements in any order.
"""

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.domain.pliego_ficha import PliegoFicha

# Relative tolerance for numeric (economic) fields: 0.1 % of the expected value.
FLOAT_REL_TOLERANCE = 1e-3


@dataclass(frozen=True)
class ResultadoCampo:
    """Outcome of comparing one field of one pliego against ground truth."""

    campo: str
    esperado: Any
    obtenido: Any
    correcto: bool


@dataclass(frozen=True)
class EvaluacionPliego:
    """Comparison results of one pliego plus its extracted dossier.

    ``ficha_obtenida`` is ``None`` when the extraction itself failed; that
    pliego is excluded from the evidence-verification percentage.
    """

    expediente: str
    comparaciones: list[ResultadoCampo]
    ficha_obtenida: PliegoFicha | None


@dataclass(frozen=True)
class MetricasEval:
    """Aggregated metrics for the report (S8 figures)."""

    precision_por_campo: dict[str, tuple[int, int]]  # field → (correct, total)
    precision_global: tuple[int, int]  # (correct, total)
    porcentaje_verificadas: float | None  # None when no non-null extracted field
    fallos_frecuentes: list[tuple[str, int]]  # top 3, most failures first


def _canonico(valor: Any) -> Any:
    """Normalize a value (BaseModel → JSON dict) for canonical comparison."""
    if isinstance(valor, BaseModel):
        return valor.model_dump(mode="json")
    return valor


def _valores_iguales(esperado: Any, obtenido: Any) -> bool:
    """Compare one expected value against the extracted value.

    Both ``None`` → correct. Numeric values use a 0.1 % relative tolerance.
    Strings compare exactly after whitespace stripping. Lists are
    order-insensitive. Nested models/dicts compare through canonical JSON.
    """
    esperado = _canonico(esperado)
    obtenido = _canonico(obtenido)
    if esperado is None and obtenido is None:
        return True
    if esperado is None or obtenido is None:
        return False
    if isinstance(esperado, bool) or isinstance(obtenido, bool):
        return bool(esperado == obtenido)
    if isinstance(esperado, (int, float)) and isinstance(obtenido, (int, float)):
        return math.isclose(
            float(esperado), float(obtenido), rel_tol=FLOAT_REL_TOLERANCE, abs_tol=1e-9
        )
    if isinstance(esperado, str) and isinstance(obtenido, str):
        return esperado.strip() == obtenido.strip()
    if isinstance(esperado, list) and isinstance(obtenido, list):
        esperados = sorted(
            json.dumps(_canonico(item), sort_keys=True, ensure_ascii=False) for item in esperado
        )
        obtenidos = sorted(
            json.dumps(_canonico(item), sort_keys=True, ensure_ascii=False) for item in obtenido
        )
        return esperados == obtenidos
    if isinstance(esperado, dict) and isinstance(obtenido, dict):
        return json.dumps(esperado, sort_keys=True, ensure_ascii=False) == json.dumps(
            obtenido, sort_keys=True, ensure_ascii=False
        )
    return bool(esperado == obtenido)


def comparar_ficha(
    campos_esperados: Mapping[str, Any], obtenida: PliegoFicha
) -> list[ResultadoCampo]:
    """Compare every ``PliegoFicha`` field against the annotated expected values.

    ``campos_esperados`` maps field name → expected value; a field missing from
    the mapping is expected to be absent (``valor = None``), so a hallucinated
    extraction is scored as a failure and a doubly-absent field as correct.
    Returns exactly one ``ResultadoCampo`` per ``PliegoFicha`` field.
    """
    resultados: list[ResultadoCampo] = []
    for name in PliegoFicha.model_fields:
        esperado = campos_esperados.get(name)
        obtenido = getattr(obtenida, name).valor
        resultados.append(
            ResultadoCampo(
                campo=name,
                esperado=esperado,
                obtenido=obtenido,
                correcto=_valores_iguales(esperado, obtenido),
            )
        )
    return resultados


def calcular_metricas(evaluaciones: Sequence[EvaluacionPliego]) -> MetricasEval:
    """Aggregate per-field precision, global precision, % verified and top-3 failures.

    Every pliego contributes one comparison per field (both-absent counts as
    correct). The evidence-verification percentage is computed over extracted
    fields with a non-null value; pliegos whose extraction failed are excluded
    (``None`` when no non-null field was ever extracted).
    """
    correctos_por_campo: dict[str, int] = {name: 0 for name in PliegoFicha.model_fields}
    fallos_por_campo: dict[str, int] = {name: 0 for name in PliegoFicha.model_fields}
    total_global = 0
    correctos_global = 0

    for evaluacion in evaluaciones:
        for resultado in evaluacion.comparaciones:
            total_global += 1
            if resultado.correcto:
                correctos_global += 1
                correctos_por_campo[resultado.campo] += 1
            else:
                fallos_por_campo[resultado.campo] += 1

    campos_extraidos = 0
    campos_verificados = 0
    for evaluacion in evaluaciones:
        if evaluacion.ficha_obtenida is None:
            continue
        for name in PliegoFicha.model_fields:
            campo = getattr(evaluacion.ficha_obtenida, name)
            if campo.valor is not None:
                campos_extraidos += 1
                if campo.verificado:
                    campos_verificados += 1

    fallos = sorted(fallos_por_campo.items(), key=lambda item: (-item[1], item[0]))
    fallos_frecuentes = [(campo, fallos) for campo, fallos in fallos[:3] if fallos > 0]

    precision_por_campo = {
        name: (correctos_por_campo[name], len(evaluaciones)) for name in correctos_por_campo
    }
    return MetricasEval(
        precision_por_campo=precision_por_campo,
        precision_global=(correctos_global, total_global),
        porcentaje_verificadas=(
            100.0 * campos_verificados / campos_extraidos if campos_extraidos else None
        ),
        fallos_frecuentes=fallos_frecuentes,
    )
