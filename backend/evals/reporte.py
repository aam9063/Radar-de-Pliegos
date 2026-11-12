"""Spanish Markdown report generation for the evaluation run (RP-08 / S8).

The report is human-facing (Albert), so its text is Spanish; the figures it
embeds come from ``evals.comparacion.calcular_metricas``. File naming is
``<fecha>.md``; if that file already exists (a same-day rerun), the time is
appended (``<fecha>-HHMM.md``) so no previous run is ever overwritten.
"""

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from evals.comparacion import MetricasEval


def _porcentaje(valor: float, decimales: int = 1) -> str:
    """Format a 0-100 percentage with Spanish decimal comma."""
    return f"{round(valor, decimales):.{decimales}f}".replace(".", ",") + " %"


def generar_informe(
    metricas: MetricasEval,
    *,
    evaluados: int,
    fallidos: int,
    pliegos: Sequence[tuple[str, str]],
) -> str:
    """Render the evaluation report: the four S8 figures plus a per-field table.

    ``pliegos`` lists ``(expediente, estado)`` pairs, e.g.
    ``("X-1", "correcto")`` or ``("X-2", "fallo: LLMRateLimitError ...")``.
    """
    correctos, total = metricas.precision_global
    precision_global = _porcentaje(100.0 * correctos / total) if total else "no disponible"
    verificadas = (
        _porcentaje(metricas.porcentaje_verificadas)
        if metricas.porcentaje_verificadas is not None
        else "no disponible (ningún campo extraído)"
    )

    lineas: list[str] = [
        "# Informe de evaluación — Radar de Pliegos",
        "",
        f"**Pliegos evaluados:** {evaluados} pliego(s) evaluado(s), {fallidos} con fallo.",
        "",
        "## Pliegos",
        "",
    ]
    for expediente, estado in pliegos:
        lineas.append(f"- `{expediente}` — {estado}")
    lineas += [
        "",
        "## Precisión global",
        "",
        f"**{correctos}/{total} valores correctos ({precision_global})**",
        "",
        "## Evidencias verificadas",
        "",
        f"**{verificadas}** de los campos extraídos (no nulos) tienen evidencia verificada.",
        "",
        "## Fallos más frecuentes",
        "",
    ]
    if metricas.fallos_frecuentes:
        for campo, fallos in metricas.fallos_frecuentes:
            lineas.append(f"- `{campo}`: {fallos} fallo(s)")
    else:
        lineas.append("Sin fallos.")
    lineas += [
        "",
        "## Precisión por campo",
        "",
        "| Campo | Correctos | Total | Precisión |",
        "| --- | --- | --- | --- |",
    ]
    for campo, (correctos_campo, total_campo) in metricas.precision_por_campo.items():
        precision = _porcentaje(100.0 * correctos_campo / total_campo) if total_campo else "n/d"
        lineas.append(f"| {campo} | {correctos_campo} | {total_campo} | {precision} |")
    lineas.append("")
    return "\n".join(lineas)


def generar_nombre_informe(dir_resultados: Path, fecha: str, ahora: datetime) -> Path:
    """``<fecha>.md``, or ``<fecha>-HHMM.md`` when today's report already exists."""
    ruta = dir_resultados / f"{fecha}.md"
    if ruta.exists():
        ruta = dir_resultados / f"{fecha}-{ahora:%H%M}.md"
    return ruta


def escribir_informe(ruta_informe: Path, contenido: str) -> Path:
    """Create the report's parent directory if needed and write the report."""
    ruta_informe.parent.mkdir(parents=True, exist_ok=True)
    ruta_informe.write_text(contenido, encoding="utf-8")
    return ruta_informe
