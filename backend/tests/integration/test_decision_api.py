"""Integration tests for the decision endpoint (S6, RP-06 / AC-06).

They run against the real Postgres (docker compose) with the ASGI transport
and a scripted ``FakeLLMClient`` used ONLY for the 3-5 sentence summary: the
deterministic engine itself is a domain function without LLM access.
"""

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient
from pytest import mark
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.adapters.fake_llm_client import FakeLLMClient
from app.db.models import Decision, Ficha
from app.domain.llm import LLMInvalidJSONError

PERFIL = {
    "clasificaciones": [{"grupo": "1", "subgrupo": "1", "categoria": "b"}],
    "volumen_anual": 2_000_000.0,
    "provincias": ["Madrid"],
    "tipos_obra": ["construcción"],
    "rango_presupuesto": {"min": 1_000_000.0, "max": 5_000_000.0},
    "dias_minimos": 10,
}

RESUMEN = "El pliego encaja con el perfil de la empresa: se recomienda presentar oferta."


def _campo(valor: object, confianza: str = "alta", verificado: bool = True) -> dict[str, Any]:
    return {
        "valor": valor,
        "evidencia": [],
        "confianza": confianza,
        "verificado": verificado,
    }


def _datos_go() -> dict[str, Any]:
    deadline = (date.today() + timedelta(days=30)).isoformat()
    return {
        "objeto": _campo("Ampliación de hospital"),
        "presupuesto_base_sin_iva": _campo(1_000_000.0),
        "fecha_limite_presentacion": _campo(deadline),
        "clasificacion_exigida": _campo([{"grupo": "1", "subgrupo": "1", "categoria": "a"}]),
        "solvencia_economica": _campo(["Cifra anual de negocios: 500.000 EUR"]),
    }


def _datos_nogo() -> dict[str, Any]:
    """Insufficient solvency (6M > 2M volume): deterministic NO-GO."""
    deadline = (date.today() + timedelta(days=30)).isoformat()
    return {
        "objeto": _campo("Ampliación de hospital"),
        "presupuesto_base_sin_iva": _campo(1_000_000.0),
        "fecha_limite_presentacion": _campo(deadline),
        "clasificacion_exigida": _campo([{"grupo": "1", "subgrupo": "1", "categoria": "a"}]),
        "solvencia_economica": _campo(["Cifra anual de negocios: 6.000.000,00 EUR"]),
    }


async def _crear_licitacion_con_ficha(
    client: AsyncClient, session_maker: async_sessionmaker[AsyncSession], datos: dict[str, Any]
) -> int:
    response = await client.post("/licitaciones", json={"nombre": "Obra de prueba"})
    assert response.status_code == 201, response.text
    licitacion_id = int(response.json()["id"])  # type: ignore[arg-type]

    async with session_maker() as session:
        session.add(Ficha(licitacion_id=licitacion_id, datos=datos, modelo="fake", avisos=[]))
        await session.commit()
    return licitacion_id


@mark.parametrize("llm_client", [[{"resumen": RESUMEN}]], indirect=True)
async def test_decision_round_trip_persists_and_uses_llm_only_for_summary(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    http, session_maker = client
    await http.put("/perfil", json=PERFIL)
    licitacion_id = await _crear_licitacion_con_ficha(http, session_maker, _datos_go())

    response = await http.get(f"/licitaciones/{licitacion_id}/decision")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resultado"] == "GO"
    assert body["razones"] == []
    assert body["resumen"] == RESUMEN

    # The LLM was called exactly once, only to summarize the computed reasons.
    assert len(llm_client.calls) == 1
    call = llm_client.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert '"razones"' in call["prompt"]
    assert "GO" in call["prompt"]

    # The decision row is persisted and re-evaluation replaces it (single row).
    async with session_maker() as session:
        decisiones = (await session.scalars(select(Decision))).all()
    assert len(decisiones) == 1
    decision = decisiones[0]
    assert decision.licitacion_id == licitacion_id
    assert decision.resultado == "GO"
    assert decision.razones == []
    assert decision.resumen == RESUMEN

    second = await http.get(f"/licitaciones/{licitacion_id}/decision")
    assert second.status_code == 200
    async with session_maker() as session:
        total = await session.scalar(select(func.count()).select_from(Decision))
    assert total == 1


@mark.parametrize("llm_client", [[{"resumen": RESUMEN}]], indirect=True)
async def test_decision_nogo_razones_keep_field_and_level(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    http, session_maker = client
    await http.put("/perfil", json=PERFIL)
    licitacion_id = await _crear_licitacion_con_ficha(http, session_maker, _datos_nogo())

    response = await http.get(f"/licitaciones/{licitacion_id}/decision")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["resultado"] == "NO-GO"
    assert len(body["razones"]) == 1
    razon = body["razones"][0]
    assert razon["campo"] == "solvencia_economica"
    assert razon["nivel"] == "NO-GO"
    assert razon["descripcion"]
    # The summary prompt is built from the computed reasons only.
    assert '"solvencia_economica"' in llm_client.calls[0]["prompt"]
    assert "NO-GO" in llm_client.calls[0]["prompt"]


@mark.parametrize("llm_client", [[{"resumen": RESUMEN}]], indirect=True)
async def test_decision_without_ficha_is_404(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    http, _session_maker = client
    await http.put("/perfil", json=PERFIL)

    created = await http.post("/licitaciones", json={"nombre": "Sin pliego"})
    licitacion_id = int(created.json()["id"])  # type: ignore[arg-type]

    response = await http.get(f"/licitaciones/{licitacion_id}/decision")

    assert response.status_code == 404
    assert "ficha" in response.json()["detail"]
    assert llm_client.calls == []


@mark.parametrize("llm_client", [[{"resumen": RESUMEN}]], indirect=True)
async def test_decision_without_profile_is_409(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    http, session_maker = client
    licitacion_id = await _crear_licitacion_con_ficha(http, session_maker, _datos_go())

    response = await http.get(f"/licitaciones/{licitacion_id}/decision")

    assert response.status_code == 409
    assert "perfil" in response.json()["detail"]
    assert llm_client.calls == []


@mark.parametrize("llm_client", [[LLMInvalidJSONError("not json")]], indirect=True)
async def test_decision_llm_failure_returns_502_and_persists_nothing(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
    llm_client: FakeLLMClient,
) -> None:
    http, session_maker = client
    await http.put("/perfil", json=PERFIL)
    licitacion_id = await _crear_licitacion_con_ficha(http, session_maker, _datos_go())

    response = await http.get(f"/licitaciones/{licitacion_id}/decision")

    assert response.status_code == 502
    async with session_maker() as session:
        total = await session.scalar(select(func.count()).select_from(Decision))
    assert total == 0
