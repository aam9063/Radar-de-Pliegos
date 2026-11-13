"""Endpoints for stored documents: serve the original PDF (S1, AC-09 viewer)."""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.db.models import Documento
from app.db.session import get_session

router = APIRouter(tags=["documentos"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def resolve_pdf_path(storage_dir: str, ruta: str) -> Path:
    """Resolve the stored relative path strictly inside ``storage_dir``.

    Raises ``FileNotFoundError`` when the path escapes the storage directory
    (path traversal) so callers can map it to a 404 without leaking details.
    """
    storage = Path(storage_dir).resolve()
    candidate = (storage / ruta).resolve()
    if not candidate.is_relative_to(storage):
        raise FileNotFoundError(ruta)
    return candidate


@router.get("/documentos/{documento_id}/pdf", response_class=FileResponse)
async def descargar_pdf(
    documento_id: int,
    session: SessionDep,
    settings: SettingsDep,
) -> FileResponse:
    """Serve the original uploaded PDF of a document (S1: guardar el PDF original)."""
    documento = await session.get(Documento, documento_id)
    if documento is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El documento {documento_id} no existe",
        )

    try:
        pdf_path = resolve_pdf_path(settings.storage_dir, documento.ruta)
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El fichero del documento {documento_id} no está disponible",
        ) from exc

    if not pdf_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"El fichero del documento {documento_id} no está disponible",
        )

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=documento.nombre_fichero,
        content_disposition_type="inline",
        headers={"Cache-Control": "private, max-age=300"},
    )
