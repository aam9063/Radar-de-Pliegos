"""SQLAlchemy 2 async models for the MVP schema (RP-02).

Only `licitacion`, `documento` and `pagina` live here for now; ficha,
perfil_empresa and decision arrive with RP-04/RP-06.
"""

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TipoDocumento(enum.StrEnum):
    PCAP = "PCAP"
    PPT = "PPT"
    ANEXO = "ANEXO"
    OTRO = "OTRO"


class EstadoLicitacion(enum.StrEnum):
    PENDIENTE = "pendiente"
    PROCESANDO = "procesando"
    LISTA = "lista"
    ERROR = "error"


class Licitacion(Base):
    __tablename__ = "licitacion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nombre: Mapped[str] = mapped_column(String(255), nullable=False)
    creada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    estado: Mapped[EstadoLicitacion] = mapped_column(
        Enum(
            EstadoLicitacion,
            name="estado_licitacion",
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
        default=EstadoLicitacion.PENDIENTE,
    )

    documentos: Mapped[list[Documento]] = relationship(
        back_populates="licitacion", cascade="all, delete-orphan"
    )


class Documento(Base):
    __tablename__ = "documento"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    licitacion_id: Mapped[int] = mapped_column(
        ForeignKey("licitacion.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[TipoDocumento] = mapped_column(
        Enum(
            TipoDocumento,
            name="tipo_documento",
            values_callable=lambda e: [member.value for member in e],
        ),
        nullable=False,
    )
    nombre_fichero: Mapped[str] = mapped_column(String(255), nullable=False)
    ruta: Mapped[str] = mapped_column(String(1024), nullable=False)
    num_paginas: Mapped[int] = mapped_column(Integer, nullable=False)

    licitacion: Mapped[Licitacion] = relationship(back_populates="documentos")
    paginas: Mapped[list[Pagina]] = relationship(
        back_populates="documento", cascade="all, delete-orphan"
    )


class Pagina(Base):
    __tablename__ = "pagina"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    documento_id: Mapped[int] = mapped_column(
        ForeignKey("documento.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sin_texto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    documento: Mapped[Documento] = relationship(back_populates="paginas")
