"""Ground truth annotation schema for the evaluation set (RP-08 / S8).

The annotation format is designed to be written by hand (by Albert): one JSON
file per pliego under ``<data-dir>/ground_truth/<expediente>.json``. Fields can
be annotated either as a bare value (``"objeto": "texto"``) or wrapped in an
object with an optional ``nota`` comment (``"objeto": {"valor": "texto",
"nota": "página 4"}``). A field not present in ``campos`` means the datum is
expected to be absent in the dossier.

Files whose name starts with ``_`` (like the ``_ejemplo.json`` template) are
ignored by the runner.
"""

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.domain.pliego_ficha import PliegoFicha

DocumentoTipo = Literal["PCAP", "ANEXO", "PPT", "OTRO"]


class GroundTruthInvalida(Exception):
    """A ground truth file could not be parsed or an annotated value is invalid."""


class DocumentoPliego(BaseModel):
    """One PDF of the pliego and its document type (used for prompt markers)."""

    tipo: DocumentoTipo
    archivo: str  # file name inside the ``pliegos/`` data directory


class GroundTruth(BaseModel):
    """Human annotation of one pliego: its PDFs plus the expected field values."""

    expediente: str
    documentos: list[DocumentoPliego] = Field(min_length=1)
    campos: dict[str, Any] = {}

    @field_validator("campos")
    @classmethod
    def campos_son_campos_de_pliegoficha(cls, campos: dict[str, Any]) -> dict[str, Any]:
        desconocidos = sorted(set(campos) - set(PliegoFicha.model_fields))
        if desconocidos:
            raise ValueError("campo desconocido(s) en ground truth: " + ", ".join(desconocidos))
        return campos

    def campos_esperados(self) -> dict[str, Any]:
        """Normalize ``campos`` to field name → expected raw value.

        Accepts the bare-value shorthand and the ``{"valor": ..., "nota": ...}``
        wrapper; an annotated wrapper without a ``valor`` key counts as an
        expected null value.
        """
        normalizados: dict[str, Any] = {}
        for nombre, anotacion in self.campos.items():
            if isinstance(anotacion, dict):
                normalizados[nombre] = anotacion.get("valor")
            else:
                normalizados[nombre] = anotacion
        return normalizados

    def ficha_esperada(self) -> PliegoFicha:
        """Validate the annotated values against ``PliegoFicha``.

        Raises ``GroundTruthInvalida`` when an annotated value does not conform
        to the field's type, so annotation mistakes are caught at load time.
        """
        try:
            return PliegoFicha.model_validate(
                {name: {"valor": valor} for name, valor in self.campos_esperados().items()}
            )
        except ValidationError as exc:
            raise GroundTruthInvalida(
                f"ground truth de '{self.expediente}' no valida contra PliegoFicha: {exc}"
            ) from exc


def cargar_ground_truths(dir_ground_truth: Path) -> list[GroundTruth]:
    """Load every annotated pliego, sorted by file name.

    Files starting with ``_`` are templates and are skipped. Any unreadable or
    invalid file raises ``GroundTruthInvalida`` naming the offending file.
    """
    cargados: list[GroundTruth] = []
    for ruta in sorted(dir_ground_truth.glob("*.json")):
        if ruta.name.startswith("_"):
            continue
        try:
            data = json.loads(ruta.read_text(encoding="utf-8"))
            cargados.append(GroundTruth.model_validate(data))
        except (json.JSONDecodeError, ValidationError, OSError) as exc:
            raise GroundTruthInvalida(f"{ruta.name}: {exc}") from exc
    return cargados
