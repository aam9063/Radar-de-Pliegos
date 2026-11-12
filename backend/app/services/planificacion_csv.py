"""CSV export of a CPM plan (BRIEF S9, RP-10, AC-13).

Presentation-level serialization for the ``planificacion.csv`` endpoint: the
plan is ordered by early start (then name), UTF-8 with BOM so Excel opens the
accents correctly, and criticality as ``Sí``/``No``.
"""

import csv
import io

from app.domain.planificacion import PlanificacionCPM

CSV_HEADERS = [
    "Actividad",
    "Duración (días)",
    "Predecesoras",
    "Inicio temprano",
    "Fin temprano",
    "Inicio tardío",
    "Fin tardío",
    "Holgura (días)",
    "Crítica",
]


def planificacion_a_csv(plan: PlanificacionCPM) -> bytes:
    """Serialize the CPM plan as CSV bytes (UTF-8 with BOM)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_HEADERS)
    for actividad in sorted(plan.actividades, key=lambda a: (a.inicio_temprano, a.nombre)):
        writer.writerow(
            [
                actividad.nombre,
                actividad.duracion_dias,
                "; ".join(actividad.predecesoras),
                actividad.inicio_temprano,
                actividad.fin_temprano,
                actividad.inicio_tardio,
                actividad.fin_tardio,
                actividad.holgura,
                "Sí" if actividad.es_critica else "No",
            ]
        )
    return buffer.getvalue().encode("utf-8-sig")
