"""Endpoints for the single editable company profile (S5, RP-06)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.perfil_empresa import PerfilEmpresa
from app.services.perfil_service import guardar_perfil, obtener_perfil

router = APIRouter(tags=["perfil"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/perfil", response_model=PerfilEmpresa | None)
async def leer_perfil(session: SessionDep) -> PerfilEmpresa | None:
    """Return the stored company profile, or null while not configured yet."""
    return await obtener_perfil(session)


@router.put("/perfil", response_model=PerfilEmpresa)
async def guardar_perfil_actual(payload: PerfilEmpresa, session: SessionDep) -> PerfilEmpresa:
    """Create or replace (single row) the company profile."""
    return await guardar_perfil(session, payload)
