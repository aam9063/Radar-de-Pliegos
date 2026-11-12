"""Integration tests for the company profile endpoints (S5, RP-06).

They run against the real Postgres (docker compose) with the ASGI transport.
The profile is a single editable row: PUT replaces it, GET returns it or
``null`` while it has never been configured.
"""

from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import PerfilEmpresa as PerfilEmpresaRow

PERFIL = {
    "clasificaciones": [{"grupo": "1", "subgrupo": "1", "categoria": "b"}],
    "volumen_anual": 2_000_000.0,
    "provincias": ["Madrid", "Toledo"],
    "tipos_obra": ["construcción", "reforma"],
    "rango_presupuesto": {"min": 1_000_000.0, "max": 5_000_000.0},
    "dias_minimos": 10,
}


async def test_perfil_get_without_configuration_returns_null(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    http, _session_maker = client

    response = await http.get("/perfil")

    assert response.status_code == 200
    assert response.json() is None


async def test_perfil_put_then_get_round_trips(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    http, _session_maker = client

    saved = await http.put("/perfil", json=PERFIL)
    assert saved.status_code == 200, saved.text
    assert saved.json() == PERFIL

    fetched = await http.get("/perfil")
    assert fetched.status_code == 200
    assert fetched.json() == PERFIL


async def test_perfil_put_replaces_the_single_row(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    http, session_maker = client

    await http.put("/perfil", json=PERFIL)
    cambiado = {**PERFIL, "dias_minimos": 20, "volumen_anual": 3_000_000.0}
    updated = await http.put("/perfil", json=cambiado)

    assert updated.status_code == 200
    assert updated.json() == cambiado

    fetched = await http.get("/perfil")
    assert fetched.json() == cambiado

    async with session_maker() as session:
        total = await session.scalar(select(func.count()).select_from(PerfilEmpresaRow))
    assert total == 1


async def test_perfil_put_rejects_invalid_payload(
    client: tuple[AsyncClient, async_sessionmaker[AsyncSession]],
) -> None:
    http, _session_maker = client

    invalido = {**PERFIL, "rango_presupuesto": {"min": 5_000_000.0, "max": 1_000_000.0}}
    response = await http.put("/perfil", json=invalido)

    assert response.status_code == 422
