"""Decision orchestration (S6, RP-06): pure engine plus an LLM-only summary.

The deterministic verdict is computed by the pure domain engine
``app.domain.motor_decision.evaluar`` — the LLM never decides. After the
verdict, the LLM is asked once to write a 3-5 sentence summary using ONLY the
already-computed reasons. A summary failure (provider fault or invalid
answer) propagates so the endpoint maps it to HTTP 502 without persisting
anything half-done, mirroring the extraction contract.
"""

from datetime import date
from json import dumps
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.db.models import Decision, Ficha
from app.domain.llm import LLMClient
from app.domain.motor_decision import ResultadoDecision, evaluar
from app.domain.pliego_ficha import PliegoFicha
from app.services.perfil_service import obtener_perfil


class FichaNoDisponibleError(Exception):
    """The licitación has no extracted dossier yet, so no decision is possible."""


class PerfilNoConfiguradoError(Exception):
    """No company profile is configured, which the engine requires."""


RESUMEN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"resumen": {"type": "string"}},
    "required": ["resumen"],
    "additionalProperties": False,
}

_RESUMEN_PROMPT_HEADER = """\
Eres un redactor técnico. A partir de ÚNICAMENTE del veredicto y de las razones
ya calculadas por el motor de decisión (JSON siguiente), redacta un resumen de
3 a 5 frases en español. No añadas datos nuevos, no inventes información y no
cambies el veredicto. Responde SOLO con un objeto JSON con la clave "resumen".
"""


class ResumenLLM(BaseModel):
    """Validated LLM summary answer."""

    resumen: str = Field(min_length=1)


async def _resumir(llm_client: LLMClient, model: str, veredicto: ResultadoDecision) -> str:
    """Ask the LLM once to summarize the computed verdict and reasons."""
    payload = dumps(veredicto.model_dump(mode="json"), ensure_ascii=False)
    prompt = f"{_RESUMEN_PROMPT_HEADER}\n\n{payload}"
    answer = await llm_client.complete_json(model=model, prompt=prompt, schema=RESUMEN_SCHEMA)
    return ResumenLLM.model_validate(answer).resumen


async def calcular_decision_para_licitacion(
    session: AsyncSession,
    licitacion_id: int,
    llm_client: LLMClient,
    settings: Settings,
    hoy: date,
) -> Decision:
    """Evaluate the dossier, summarize with the LLM and persist the decision.

    Raises ``FichaNoDisponibleError`` without touching the LLM when the
    licitación has no dossier yet, and ``PerfilNoConfiguradoError`` when no
    company profile exists. One decision row per licitación: re-evaluation
    replaces the previous one. The LLM call happens only after the verdict and
    never decides anything.
    """
    ficha_row = await session.scalar(select(Ficha).where(Ficha.licitacion_id == licitacion_id))
    if ficha_row is None:
        raise FichaNoDisponibleError(f"La licitación {licitacion_id} aún no tiene ficha extraída")

    perfil = await obtener_perfil(session)
    if perfil is None:
        raise PerfilNoConfiguradoError(
            "Configura primero el perfil de empresa para calcular decisiones."
        )

    ficha = PliegoFicha.model_validate(ficha_row.datos)
    veredicto = evaluar(ficha, perfil, hoy=hoy)
    resumen = await _resumir(llm_client, settings.summary_model, veredicto)

    razones = [razon.model_dump(mode="json") for razon in veredicto.razones]
    existing = await session.scalar(select(Decision).where(Decision.licitacion_id == licitacion_id))
    if existing is not None:
        existing.resultado = veredicto.resultado
        existing.razones = razones
        existing.resumen = resumen
        await session.commit()
        return existing

    row = Decision(
        licitacion_id=licitacion_id,
        resultado=veredicto.resultado,
        razones=razones,
        resumen=resumen,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row
