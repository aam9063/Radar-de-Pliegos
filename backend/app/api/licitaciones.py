"""Endpoints for licitaciones, PDF upload, structured extraction and decision."""

from datetime import date
from typing import Annotated

import pymupdf
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_hoy, get_llm_client
from app.api.schemas import (
    DecisionOut,
    DocumentoOut,
    FichaOut,
    LicitacionCreate,
    LicitacionOut,
)
from app.core.config import Settings, get_settings
from app.db.models import (
    Decision,
    Documento,
    EstadoLicitacion,
    Ficha,
    Licitacion,
    Pagina,
    TipoDocumento,
)
from app.db.session import get_session
from app.domain.llm import LLMClient, LLMError
from app.domain.pliego_ficha import ExtractionInvalidOutputError
from app.services.decision_service import (
    FichaNoDisponibleError,
    PerfilNoConfiguradoError,
    calcular_decision_para_licitacion,
)
from app.services.document_storage import save_pdf
from app.services.ficha_extraction import extract_ficha_for_licitacion
from app.services.page_extraction import extract_pages

router = APIRouter(tags=["licitaciones"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
LLMDep = Annotated[LLMClient, Depends(get_llm_client)]
HoyDep = Annotated[date, Depends(get_hoy)]


@router.post(
    "/licitaciones",
    response_model=LicitacionOut,
    status_code=status.HTTP_201_CREATED,
)
async def crear_licitacion(
    payload: LicitacionCreate,
    session: SessionDep,
) -> Licitacion:
    licitacion = Licitacion(nombre=payload.nombre, estado=EstadoLicitacion.PENDIENTE)
    session.add(licitacion)
    await session.commit()
    await session.refresh(licitacion)
    return licitacion


@router.get("/licitaciones", response_model=list[LicitacionOut])
async def listar_licitaciones(session: SessionDep) -> list[Licitacion]:
    result = await session.execute(select(Licitacion).order_by(Licitacion.id))
    return list(result.scalars().all())


@router.post(
    "/licitaciones/{licitacion_id}/documentos",
    response_model=DocumentoOut,
    status_code=status.HTTP_201_CREATED,
)
async def subir_documento(
    licitacion_id: int,
    file: UploadFile,
    tipo: Annotated[TipoDocumento, Form()],
    session: SessionDep,
    settings: SettingsDep,
) -> Documento:
    licitacion = await session.get(Licitacion, licitacion_id)
    if licitacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La licitación {licitacion_id} no existe",
        )

    content = await file.read()
    try:
        pages = extract_pages(content)
    except (pymupdf.FileDataError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El fichero no es un PDF válido",
        ) from exc

    ruta = save_pdf(settings.storage_dir, licitacion_id, content)

    documento = Documento(
        licitacion_id=licitacion_id,
        tipo=tipo,
        nombre_fichero=file.filename or "documento.pdf",
        ruta=ruta,
        num_paginas=len(pages),
    )
    session.add(documento)
    await session.flush()

    for page in pages:
        session.add(
            Pagina(
                documento_id=documento.id,
                numero=page.numero,
                texto=page.texto,
                sin_texto=page.sin_texto,
            )
        )
    await session.commit()
    await session.refresh(documento)
    return documento


async def _get_licitacion_or_404(session: AsyncSession, licitacion_id: int) -> Licitacion:
    licitacion = await session.get(Licitacion, licitacion_id)
    if licitacion is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La licitación {licitacion_id} no existe",
        )
    return licitacion


@router.post("/licitaciones/{licitacion_id}/extraer", response_model=FichaOut)
async def extraer_ficha(
    licitacion_id: int,
    session: SessionDep,
    settings: SettingsDep,
    llm_client: LLMDep,
) -> Ficha:
    """Extract the structured dossier of a licitación (BRIEF §9, S3).

    Nothing is persisted when the LLM answer is invalid even after the single
    retry: both that and provider faults map to a clear HTTP 502.
    """
    licitacion = await _get_licitacion_or_404(session, licitacion_id)
    try:
        return await extract_ficha_for_licitacion(session, licitacion, llm_client, settings)
    except ExtractionInvalidOutputError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except LLMError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El proveedor de IA no completó la extracción del pliego.",
        ) from exc


@router.get("/licitaciones/{licitacion_id}/ficha", response_model=FichaOut)
async def obtener_ficha(licitacion_id: int, session: SessionDep) -> Ficha:
    """Return the persisted dossier of a licitación, or 404 if not extracted yet."""
    await _get_licitacion_or_404(session, licitacion_id)
    ficha = await session.scalar(select(Ficha).where(Ficha.licitacion_id == licitacion_id))
    if ficha is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"La licitación {licitacion_id} aún no tiene ficha extraída",
        )
    return ficha


@router.get("/licitaciones/{licitacion_id}/decision", response_model=DecisionOut)
async def decidir_licitacion(
    licitacion_id: int,
    session: SessionDep,
    settings: SettingsDep,
    llm_client: LLMDep,
    hoy: HoyDep,
) -> Decision:
    """Compute the deterministic decision (S6) and persist it.

    The engine is pure code, never the LLM; the LLM is asked afterwards to
    write the 3-5 sentence summary from the already-computed reasons only. A
    summary failure maps to HTTP 502 without persisting anything half-done.
    """
    await _get_licitacion_or_404(session, licitacion_id)
    try:
        return await calcular_decision_para_licitacion(
            session, licitacion_id, llm_client, settings, hoy
        )
    except FichaNoDisponibleError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PerfilNoConfiguradoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except (LLMError, ValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="El proveedor de IA no pudo redactar el resumen de la decisión.",
        ) from exc
