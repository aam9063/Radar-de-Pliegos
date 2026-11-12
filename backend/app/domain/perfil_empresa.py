"""Company profile domain schema (S5, RP-06).

Pure Pydantic v2 models: no FastAPI, SQLAlchemy or AI SDK imports
(architecture rule, AGENTS.md section 8). The profile is a single editable
record describing what the company can bid for.
"""

from pydantic import BaseModel, Field, model_validator


class ClasificacionEmpresa(BaseModel):
    """One contractor classification the company owns (grupo/subgrupo/categoría)."""

    grupo: str
    subgrupo: str
    categoria: str | None = None


class RangoPresupuesto(BaseModel):
    """Budget range of interest, inclusive bounds in euros (sin IVA)."""

    min: float = Field(ge=0)
    max: float = Field(ge=0)

    @model_validator(mode="after")
    def min_not_above_max(self) -> RangoPresupuesto:
        if self.min > self.max:
            raise ValueError("el mínimo del rango no puede superar el máximo")
        return self


class PerfilEmpresa(BaseModel):
    """Single company profile (S5): classifications, capacity and interests."""

    clasificaciones: list[ClasificacionEmpresa] = []
    volumen_anual: float = Field(ge=0)
    provincias: list[str] = []
    tipos_obra: list[str] = []
    rango_presupuesto: RangoPresupuesto
    dias_minimos: int = Field(ge=0)
