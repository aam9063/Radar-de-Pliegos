"""Unit tests for the Spanish Markdown report generation (RP-08 / S8)."""

from datetime import datetime

from evals.comparacion import MetricasEval
from evals.reporte import escribir_informe, generar_informe, generar_nombre_informe


def _metricas() -> MetricasEval:
    return MetricasEval(
        precision_por_campo={"expediente": (3, 5), "objeto": (2, 5), "cpv": (5, 5)},
        precision_global=(10, 15),
        porcentaje_verificadas=66.666,
        fallos_frecuentes=[("objeto", 3), ("garantia_provisional", 1)],
    )


def test_informe_incluye_las_cuatro_cifras_y_tabla() -> None:
    informe = generar_informe(
        _metricas(),
        evaluados=5,
        fallidos=0,
        pliegos=[("X-1", "correcto"), ("X-2", "correcto")],
    )
    assert "# Informe de evaluación" in informe
    assert "## Precisión global" in informe
    assert "10/15" in informe
    assert "66,7" in informe  # Spanish decimal comma
    assert "## Evidencias verificadas" in informe
    assert "## Fallos más frecuentes" in informe
    assert "objeto" in informe and "garantia_provisional" in informe
    assert "## Precisión por campo" in informe
    assert "| Campo | Correctos | Total | Precisión |" in informe
    assert "| expediente | 3 | 5 |" in informe
    assert "| cpv | 5 | 5 |" in informe


def test_informe_indica_pliegos_evaluados_y_fallidos() -> None:
    informe = generar_informe(
        _metricas(),
        evaluados=5,
        fallidos=1,
        pliegos=[("X-1", "correcto"), ("X-2", "fallo: LLMRateLimitError")],
    )
    assert "5 pliego(s) evaluado(s)" in informe
    assert "1 con fallo" in informe
    assert "- `X-1` — correcto" in informe
    assert "- `X-2` — fallo: LLMRateLimitError" in informe


def test_informe_sin_fallos_no_muestra_seccion_vacia() -> None:
    metricas = MetricasEval(
        precision_por_campo={"expediente": (5, 5)},
        precision_global=(5, 5),
        porcentaje_verificadas=100.0,
        fallos_frecuentes=[],
    )
    informe = generar_informe(metricas, evaluados=5, fallidos=0, pliegos=[])
    assert "Sin fallos." in informe


def test_informe_porcentaje_verificadas_no_disponible() -> None:
    metricas = MetricasEval(
        precision_por_campo={"expediente": (5, 5)},
        precision_global=(5, 5),
        porcentaje_verificadas=None,
        fallos_frecuentes=[],
    )
    assert "no disponible" in generar_informe(metricas, evaluados=5, fallidos=0, pliegos=[])


def test_nombre_informe_usa_la_fecha(tmp_path) -> None:
    ahora = datetime(2026, 11, 12, 15, 30)
    assert generar_nombre_informe(tmp_path, "2026-11-12", ahora) == tmp_path / "2026-11-12.md"


def test_nombre_informe_evita_sobrescribir_con_hora(tmp_path) -> None:
    ahora = datetime(2026, 11, 12, 15, 30)
    (tmp_path / "2026-11-12.md").write_text("previo", encoding="utf-8")
    assert generar_nombre_informe(tmp_path, "2026-11-12", ahora) == tmp_path / "2026-11-12-1530.md"


def test_escribir_informe_crea_directorio_y_fichero(tmp_path) -> None:
    destino = tmp_path / "results" / "2026-11-12.md"
    ruta = escribir_informe(destino, "CONTENIDO")
    assert ruta.exists()
    assert ruta.parent == destino.parent
    assert ruta.read_text(encoding="utf-8") == "CONTENIDO"
