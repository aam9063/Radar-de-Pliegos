"""Domain schema for the structured tender dossier ``PliegoFicha`` (BRIEF S3, RP-04).

Pure Pydantic v2 models: no FastAPI, SQLAlchemy or AI SDK imports (architecture
rule, AGENTS.md section 8).

Golden rule (S3): if a datum does not appear in the pliego, the field keeps
``valor = None`` and empty ``evidencia``. It is never invented nor inferred,
which is why every ``CampoExtraido`` field defaults to a null extraction.
"""

from enum import StrEnum
from typing import TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")

MAX_CITA_WORDS = 30


class Confianza(StrEnum):
    """Confidence the model reports for each extracted field."""

    ALTA = "alta"
    MEDIA = "media"
    BAJA = "baja"


class Evidencia(BaseModel):
    """Literal citation backing an extracted value (document type + page)."""

    documento: str
    pagina: int = Field(ge=1)
    cita: str

    @field_validator("cita")
    @classmethod
    def cita_has_at_most_30_words(cls, value: str) -> str:
        words = value.split()
        if len(words) > MAX_CITA_WORDS:
            raise ValueError(
                f"la cita debe tener {MAX_CITA_WORDS} palabras como máximo (tiene {len(words)})"
            )
        return value


class CampoExtraido[T](BaseModel):
    """One extracted field: value plus the evidence that supports it.

    ``verificado`` records the deterministic evidence check (S4, RP-05): it
    stays ``True`` unless one of the field's evidencias could not be matched
    against the cited page's text.
    """

    valor: T | None = None
    evidencia: list[Evidencia] = []
    confianza: Confianza = Confianza.BAJA
    verificado: bool = True


class RevisionPrecios(BaseModel):
    """Whether price revision applies, plus the formula when it appears."""

    aplica: bool | None = None
    formula: str | None = None


class PlazoEjecucion(BaseModel):
    """Execution deadline as magnitude plus unit (e.g. "12" + "meses")."""

    valor: str | None = None
    unidad: str | None = None


class TipoCriterio(StrEnum):
    """Adjudication criteria kind: objective formulas vs value judgement."""

    AUTOMATICO = "automatico"
    JUICIO_VALOR = "juicio_valor"


class CriterioAdjudicacion(BaseModel):
    """One adjudication criterion with its weight in points or percent."""

    nombre: str
    tipo: TipoCriterio
    ponderacion: str


class ClasificacionRequerida(BaseModel):
    """Required contractor classification: group / subgroup / category."""

    grupo: str
    subgrupo: str
    categoria: str | None = None


class ExtractionInvalidOutputError(Exception):
    """The LLM answer failed ``PliegoFicha`` validation after the single retry.

    Raised only after the second failure so callers can map it to a clear
    HTTP 502 without persisting any partial dossier.
    """


class PliegoFicha(BaseModel):
    """Complete structured dossier of a pliego (BRIEF S3)."""

    # Identificación
    expediente: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    objeto: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    organo_contratacion: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    cpv: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    procedimiento: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    tramitacion: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    # Económicos
    presupuesto_base_sin_iva: CampoExtraido[float] = Field(default_factory=CampoExtraido[float])
    presupuesto_base_con_iva: CampoExtraido[float] = Field(default_factory=CampoExtraido[float])
    valor_estimado: CampoExtraido[float] = Field(default_factory=CampoExtraido[float])
    revision_precios: CampoExtraido[RevisionPrecios] = Field(
        default_factory=CampoExtraido[RevisionPrecios]
    )
    # Plazos
    plazo_ejecucion: CampoExtraido[PlazoEjecucion] = Field(
        default_factory=CampoExtraido[PlazoEjecucion]
    )
    fecha_limite_presentacion: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    # Requisitos
    clasificacion_exigida: CampoExtraido[list[ClasificacionRequerida]] = Field(
        default_factory=CampoExtraido[list[ClasificacionRequerida]]
    )
    solvencia_economica: CampoExtraido[list[str]] = Field(default_factory=CampoExtraido[list[str]])
    solvencia_tecnica: CampoExtraido[list[str]] = Field(default_factory=CampoExtraido[list[str]])
    # Adjudicación
    criterios_adjudicacion: CampoExtraido[list[CriterioAdjudicacion]] = Field(
        default_factory=CampoExtraido[list[CriterioAdjudicacion]]
    )
    # Riesgos
    penalidades: CampoExtraido[list[str]] = Field(default_factory=CampoExtraido[list[str]])
    garantia_provisional: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    garantia_definitiva: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
    subcontratacion_limites: CampoExtraido[str] = Field(default_factory=CampoExtraido[str])
