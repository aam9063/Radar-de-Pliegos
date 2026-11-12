"""Endpoints for licitaciones and PDF upload (BRIEF §9, AC-02)."""

from typing import Annotated

import pymupdf
from fastapi import APIRouter, Depends, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import DocumentoOut, LicitacionCreate, LicitacionOut
from app.core.config import Settings, get_settings
from app.db.models import Documento, EstadoLicitacion, Licitacion, Pagina, TipoDocumento
from app.db.session import get_session
from app.services.document_storage import save_pdf
from app.services.page_extraction import extract_pages

router = APIRouter(tags=["licitaciones"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


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
