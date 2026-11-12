"""Deterministic fusion of per-document ``PliegoFicha`` results (S3, RP-05 / AC-07).

Pure domain rule: merge N per-document extractions into one dossier, field by
field, with the BRIEF source priority ``PCAP > ANEXO > PPT > OTRO``. When two
or more sources hold different non-null values for the same field, the
highest-priority value wins and a conflict ``aviso`` records the decision
(e.g. ``"presupuesto_base_sin_iva: conflicto PCAP vs PPT, gana PCAP"``).

No FastAPI, SQLAlchemy or AI SDK imports (architecture rule, AGENTS.md §8).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.domain.pliego_ficha import PliegoFicha

# BRIEF S3 source priority when sources conflict. Lower rank wins.
SOURCE_PRIORITY: dict[str, int] = {"PCAP": 0, "ANEXO": 1, "PPT": 2, "OTRO": 3}

_UNKNOWN_SOURCE_RANK = len(SOURCE_PRIORITY)


@dataclass(frozen=True)
class FichaFuente:
    """One per-document extraction and the type of the document it came from."""

    tipo: str
    ficha: PliegoFicha


@dataclass(frozen=True)
class FusionResultado:
    """The merged dossier plus the conflict avisos recorded while fusing."""

    ficha: PliegoFicha
    avisos: list[str]


def _rank(tipo: str) -> int:
    return SOURCE_PRIORITY.get(tipo, _UNKNOWN_SOURCE_RANK)


def fusionar_fichas(fuentes: Sequence[FichaFuente]) -> FusionResultado:
    """Merge the per-document fichas field by field, highest priority wins."""
    campos: dict[str, dict[str, object]] = {}
    avisos: list[str] = []

    for name in PliegoFicha.model_fields:
        candidatos = [
            (index, fuente.tipo, getattr(fuente.ficha, name))
            for index, fuente in enumerate(fuentes)
            if getattr(fuente.ficha, name).valor is not None
        ]
        if not candidatos:
            continue  # absent everywhere → the field keeps its null defaults

        # Priority first; equal types keep the order the sources arrived in.
        candidatos.sort(key=lambda candidato: (_rank(candidato[1]), candidato[0]))
        _index, tipo_ganador, campo_ganador = candidatos[0]

        perdedores = [
            tipo for _index, tipo, campo in candidatos[1:] if campo.valor != campo_ganador.valor
        ]
        if perdedores:
            avisos.append(
                f"{name}: conflicto {tipo_ganador} vs {' vs '.join(perdedores)}, "
                f"gana {tipo_ganador}"
            )

        campos[name] = campo_ganador.model_dump()

    return FusionResultado(ficha=PliegoFicha.model_validate(campos), avisos=avisos)
