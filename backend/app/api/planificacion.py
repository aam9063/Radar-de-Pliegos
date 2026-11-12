"""Endpoints for the minimal CPM planner (BRIEF S9, RP-10, AC-13).

Both endpoints compute on demand (activity proposal from the PPT plus the pure
CPM calculation) and persist nothing: the minimal Fase 2 planner has no DB
table. A missing PPT maps to 409; an invalid LLM answer after the single retry
or a provider fault maps to a clear 502, mirroring the extraction contract.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_llm_client
from app.api.licitaciones import _get_licitacion_or_404
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.domain.llm import LLMClient, LLMError
from app.domain.pliego_ficha import Evidencia
from app.services.planificacion_csv import planificacion_a_csv
from app.services.planificacion_extraction import (
    PlanificacionCalculada,
    PlanificacionInvalidOutputError,
    PPTNoDisponibleError,
    planificar_licitacion,
)

router = APIRouter(tags=["planificacion"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]


class ActividadPlanificadaOut(BaseModel):
    nombre: str
    duracion_dias: int
    predecesoras: list[str]
    inicio_temprano: int
    fin_temprano: int
    inicio_tardio: int
    fin_tardio: int
    holgura: int
    es_critica: bool
    evidencia: list[Evidencia] = []


class PlanificacionOut(BaseModel):
    licitacion_id: int
    makespan: int
    ruta_critica: list[str]
    actividades: list[ActividadPlanificadaOut]


def _plan_out(licitacion_id: int, resultado: PlanificacionCalculada) -> PlanificacionOut:
    evidencias = {propuesta.nombre: propuesta.evidencia for propuesta in resultado.propuestas}
    actividades = [
        ActividadPlanificadaOut(
            **actividad.model_dump(), evidencia=evidencias.get(actividad.nombre, [])
        )
        for actividad in resultado.plan.actividades
    ]
    return PlanificacionOut(
        licitacion_id=licitacion_id,
        makespan=resultado.plan.makespan,
        ruta_critica=resultado.plan.ruta_critica,
        actividades=actividades,
    )


async def _planificar(
    licitacion_id: int, session: SessionDep, llm_client: LLMDep, settings: SettingsDep
) -> PlanificacionCalculada:
    """Shared orchestration with the API's typed error mapping."""
    licitacion = await _get_licitacion_or_404(session, licitacion_id)
    try:
        return await planificar_licitacion(session, licitacion, llm_client, settings)
    except PPTNoDisponibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except PlanificacionInvalidOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El proveedor de IA no pudo proponer las actividades del plan.",
        ) from exc


@router.get(
    "/licitaciones/{licitacion_id}/planificacion",
    response_model=PlanificacionOut,
)
async def obtener_planificacion(
    licitacion_id: int, session: SessionDep, llm_client: LLMDep, settings: SettingsDep
) -> PlanificacionOut:
    """Propose activities from the PPT (LLM) and compute the CPM schedule."""
    resultado = await _planificar(licitacion_id, session, llm_client, settings)
    return _plan_out(licitacion_id, resultado)


@router.get("/licitaciones/{licitacion_id}/planificacion.csv")
async def exportar_planificacion_csv(
    licitacion_id: int, session: SessionDep, llm_client: LLMDep, settings: SettingsDep
) -> Response:
    """The same plan as a downloadable CSV file."""
    resultado = await _planificar(licitacion_id, session, llm_client, settings)
    return Response(
        content=planificacion_a_csv(resultado.plan),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="planificacion-{licitacion_id}.csv"'
        },
    )
