"""API request/response schemas (FastAPI layer only, not domain)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models import EstadoLicitacion, TipoDocumento


class LicitacionCreate(BaseModel):
    nombre: str


class LicitacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nombre: str
    creada_en: datetime
    estado: EstadoLicitacion


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    licitacion_id: int
    tipo: TipoDocumento
    nombre_fichero: str
    ruta: str
    num_paginas: int
