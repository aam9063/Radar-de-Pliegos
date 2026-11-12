"""LLM proposal of activities from the PPT (BRIEF S9, RP-10, AC-13).

Mirrors the ficha extraction pattern (services layer): only the ``PPT``
document's pages are sent, marked with ``[[DOC:PPT|P:<número>]]``, the LLM is
reached through the ``LLMClient`` port, and each answer is validated against
``PropuestaActividades`` AND checked to form a valid CPM graph (durations,
known predecessors, acyclic) with a single retry. The schedule itself is then
computed by the pure deterministic domain function ``calcular_cpm`` — the LLM
never computes dates.

A licitación without a PPT document raises ``PPTNoDisponibleError`` (mapped to
HTTP 409 by the API): activities are proposed with evidence from the PPT, so
without one there is no honest plan to show.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import Settings
from app.db.models import Documento, Licitacion, TipoDocumento
from app.domain.llm import LLMClient, LLMInvalidJSONError
from app.domain.planificacion import (
    ActividadPropuesta,
    PlanificacionCPM,
    PlanificacionError,
    PropuestaActividades,
    calcular_cpm,
)
from app.services.ficha_extraction import PageText

PROPUESTA_SCHEMA: dict[str, Any] = PropuestaActividades.model_json_schema()

_PROMPT_HEADER = """\
Eres un planificador de obras. Del texto siguiente del pliego (documento PPT),
extrae la lista de actividades del proyecto con su duración estimada en días y
sus predecesoras, y responde SOLO con un objeto JSON válido conforme al esquema
``PropuestaActividades`` incluido al final.

Reglas:
- "nombre" es el nombre de la actividad tal como aparece en el pliego.
- "duracion_dias" es un entero mayor que 0.
- "predecesoras" son los nombres EXACTOS de las actividades que deben
  terminarse antes de que empiece esta; [] si no tiene ninguna.
- Cada actividad lleva "evidencia": el documento y la página marcados en el
  texto con [[DOC:<tipo>|P:<número>]], y la cita es un fragmento literal de esa
  página de 30 palabras como máximo.
- Si una actividad o su duración no aparecen en el texto, no la inventes:
  omítela.
"""

_RETRY_INSTRUCTIONS = """\
La respuesta anterior no pasó la validación del plan. Error de validación:
{error}

Corrige el problema y responde de nuevo SOLO con el objeto JSON válido.
"""


class PlanificacionInvalidOutputError(Exception):
    """The LLM answer did not yield a valid activity plan even after the retry.

    Raised only after the second failure so callers can map it to a clear
    HTTP 502 without returning a half-computed plan.
    """


class PPTNoDisponibleError(Exception):
    """The licitación has no PPT document, so no activities can be proposed."""


@dataclass(frozen=True)
class PlanificacionCalculada:
    """Proposed activities plus their deterministic CPM schedule."""

    propuestas: list[ActividadPropuesta]
    plan: PlanificacionCPM


def build_prompt_actividades(pages: Sequence[PageText]) -> str:
    """Build the activity-extraction prompt: marked PPT pages, ordered by number."""
    blocks = [
        f"[[DOC:{page.documento}|P:{page.numero}]]\n{page.texto}"
        for page in sorted(pages, key=lambda page: page.numero)
        if page.texto.strip()
    ]
    body = "\n\n".join(blocks) if blocks else "(sin texto de pliego)"
    return (
        f"{_PROMPT_HEADER}\n\n{body}\n\nEsquema PropuestaActividades:\n"
        f"{json.dumps(PROPUESTA_SCHEMA)}"
    )


def _retry_prompt(prompt: str, error: Exception) -> str:
    """Append the validation failure so the model can fix its answer."""
    return f"{prompt}\n\n{_RETRY_INSTRUCTIONS.format(error=error)}"


class PropuestasExtractor:
    """Validated activity proposal with one retry on invalid output.

    Retries (exactly once) when the answer fails ``PropuestaActividades``
    validation, is not parseable JSON, or does not form a valid CPM graph
    (typed ``PlanificacionError``). A second failure raises
    ``PlanificacionInvalidOutputError``; provider faults (rate limit, server
    errors) propagate untouched.
    """

    def __init__(self, llm_client: LLMClient, model: str) -> None:
        self._llm_client = llm_client
        self._model = model

    async def extract(self, prompt: str) -> PropuestaActividades:
        try:
            return await self._ask_and_validate(prompt)
        except (ValidationError, LLMInvalidJSONError, PlanificacionError) as first_error:
            try:
                return await self._ask_and_validate(_retry_prompt(prompt, first_error))
            except (ValidationError, LLMInvalidJSONError, PlanificacionError) as second_error:
                raise PlanificacionInvalidOutputError(
                    "La propuesta de actividades falló: la respuesta del modelo no "
                    "valida contra PropuestaActividades ni tras el reintento."
                ) from second_error

    async def _ask_and_validate(self, prompt: str) -> PropuestaActividades:
        answer = await self._llm_client.complete_json(
            model=self._model, prompt=prompt, schema=PROPUESTA_SCHEMA
        )
        propuesta = PropuestaActividades.model_validate(answer)
        # Semantic validation: the proposal must form a valid CPM graph before
        # it counts as a valid answer (unknown predecessors, cycles, durations).
        calcular_cpm(propuesta.actividades)
        return propuesta


def _paginas_ppt(documento: Documento) -> list[PageText]:
    """Collect the PPT's page texts, skipping pages without text."""
    pages = [
        PageText(documento=documento.tipo.value, numero=pagina.numero, texto=pagina.texto)
        for pagina in documento.paginas
        if not pagina.sin_texto and pagina.texto.strip()
    ]
    return sorted(pages, key=lambda page: page.numero)


async def planificar_licitacion(
    session: AsyncSession,
    licitacion: Licitacion,
    llm_client: LLMClient,
    settings: Settings,
) -> PlanificacionCalculada:
    """Propose activities from the PPT and compute their CPM schedule.

    Raises ``PPTNoDisponibleError`` without touching the LLM when the
    licitación has no PPT document. Nothing is persisted: the minimal Fase 2
    planner computes on demand (no new DB table).
    """
    documento = await session.scalar(
        select(Documento)
        .where(
            Documento.licitacion_id == licitacion.id,
            Documento.tipo == TipoDocumento.PPT,
        )
        .options(selectinload(Documento.paginas))
    )
    if documento is None:
        raise PPTNoDisponibleError(
            f"La licitación {licitacion.id} no tiene un documento PPT del que proponer actividades."
        )

    extractor = PropuestasExtractor(llm_client, settings.extraction_model)
    propuesta = await extractor.extract(build_prompt_actividades(_paginas_ppt(documento)))
    plan = calcular_cpm(propuesta.actividades)
    return PlanificacionCalculada(propuestas=propuesta.actividades, plan=plan)
