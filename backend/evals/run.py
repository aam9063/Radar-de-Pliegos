"""Evaluation runner CLI (S8 / RP-08): ``cd backend && uv run python -m evals.run``.

For each annotated pliego in ``<data-dir>/ground_truth/<expediente>.json`` the
runner loads its PDF(s) from ``<data-dir>/pliegos/``, runs the REAL extraction
pipeline (per-document ``PliegoExtractor`` → deterministic fusion → evidence
verification) against the real NaN API, compares the result against the ground
truth and writes a Spanish Markdown report to ``<data-dir>/results/<fecha>.md``.

Data directory resolution (documented in ``evals/README.md``):

1. ``--data-dir`` CLI argument, when given.
2. ``EVALS_DIR`` environment variable, when set.
3. Default: ``<repo-root>/evals`` — this works out of the box when the command
   is run as ``cd backend && uv run python -m evals.run``.

Exit code: 0 when every annotated pliego evaluated correctly, 1 when one or
more pliegos failed (their errors are recorded in the report) or on a setup
error (missing ``NAN_API_KEY``, no ground truth files). Never touches the CI:
evals use the real API and run manually or via ``evals.yml`` (workflow_dispatch).
"""

import argparse
import asyncio
import os
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from app.adapters.nan_llm_client import NanLLMClient
from app.core.config import Settings
from app.domain.llm import LLMClient, LLMError
from app.domain.pliego_ficha import ExtractionInvalidOutputError
from evals.comparacion import (
    EvaluacionPliego,
    calcular_metricas,
    comparar_ficha,
)
from evals.ejecucion import extraer_ficha_de_pdfs
from evals.ground_truth import GroundTruth, GroundTruthInvalida, cargar_ground_truths
from evals.reporte import escribir_informe, generar_informe, generar_nombre_informe

# Windows: the default ProactorEventLoop races with async TLS teardown in the
# httpx2/httpcore2/anyio stack used by the openai SDK and raises
# "RuntimeError: Event loop is closed"; the selector loop avoids that race.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def resolver_dir_datos(argumento: str | None, env_evals_dir: str | None) -> Path:
    """Resolve the evaluation data directory: --data-dir > EVALS_DIR > repo default."""
    if argumento:
        return Path(argumento)
    if env_evals_dir:
        return Path(env_evals_dir)
    return Path(__file__).resolve().parents[2] / "evals"


def _errores_recuperables() -> tuple[type[Exception], ...]:
    return (
        LLMError,
        ExtractionInvalidOutputError,
        GroundTruthInvalida,
        OSError,
    )


async def _evaluar_pliego(
    ground_truth: GroundTruth, dir_pliegos: Path, llm_client: LLMClient, model: str
) -> EvaluacionPliego:
    """Extract one annotated pliego with the real pipeline and compare it."""
    ground_truth.ficha_esperada()  # catch annotation mistakes before spending API calls
    ficha = await extraer_ficha_de_pdfs(ground_truth.documentos, dir_pliegos, llm_client, model)
    comparaciones = comparar_ficha(ground_truth.campos_esperados(), ficha)
    return EvaluacionPliego(
        expediente=ground_truth.expediente,
        comparaciones=comparaciones,
        ficha_obtenida=ficha,
    )


async def _evaluar_todos(
    ground_truths: Sequence[GroundTruth],
    dir_pliegos: Path,
    llm_client: LLMClient,
    model: str,
) -> tuple[list[EvaluacionPliego], list[tuple[str, str]]]:
    """Evaluate every pliego on a single event loop (the LLM client is shared)."""
    evaluaciones: list[EvaluacionPliego] = []
    pliegos: list[tuple[str, str]] = []
    for ground_truth in ground_truths:
        try:
            evaluacion = await _evaluar_pliego(ground_truth, dir_pliegos, llm_client, model)
        except _errores_recuperables() as exc:
            print(f"Pliego '{ground_truth.expediente}' falló: {exc}", file=sys.stderr)
            pliegos.append((ground_truth.expediente, f"fallo: {type(exc).__name__}: {exc}"))
            continue
        evaluaciones.append(evaluacion)
        pliegos.append((ground_truth.expediente, "correcto"))
    return evaluaciones, pliegos


def main(
    argv: Sequence[str] | None = None,
    *,
    llm_client: LLMClient | None = None,
    settings: Settings | None = None,
) -> int:
    """Run the evaluation and write the report. Returns the process exit code."""
    parser = argparse.ArgumentParser(
        prog="evals.run", description="Evaluación de extracción de pliegos (S8)."
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="Data directory (default: EVALS_DIR env var, else <repo-root>/evals).",
    )
    args = parser.parse_args(argv)

    settings = settings or Settings()
    if llm_client is None:
        if not settings.nan_api_key:
            print(
                "Error: NAN_API_KEY is not configured. The evaluation uses the real "
                "NaN API; set the NAN_API_KEY environment variable (or backend/.env) "
                "and retry.",
                file=sys.stderr,
            )
            return 1
        llm_client = NanLLMClient(settings)

    dir_datos = resolver_dir_datos(args.data_dir, os.environ.get("EVALS_DIR"))
    dir_pliegos = dir_datos / "pliegos"
    ground_truths = cargar_ground_truths(dir_datos / "ground_truth")
    if not ground_truths:
        print(
            f"Error: no ground truth files found in {dir_datos / 'ground_truth'}. "
            "Annotate the pliegos first (see evals/README.md).",
            file=sys.stderr,
        )
        return 1

    evaluaciones, pliegos = asyncio.run(
        _evaluar_todos(ground_truths, dir_pliegos, llm_client, settings.extraction_model)
    )

    metricas = calcular_metricas(evaluaciones)
    informe = generar_informe(
        metricas,
        evaluados=len(evaluaciones),
        fallidos=len(pliegos) - len(evaluaciones),
        pliegos=pliegos,
    )
    ahora = datetime.now()
    ruta = generar_nombre_informe(dir_datos / "results", ahora.strftime("%Y-%m-%d"), ahora)
    escribir_informe(ruta, informe)
    print(f"Informe de evaluación escrito en {ruta}")

    return 1 if len(pliegos) - len(evaluaciones) else 0


if __name__ == "__main__":
    raise SystemExit(main())
