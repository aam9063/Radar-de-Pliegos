"""Shared fixtures for integration tests (real Postgres + Alembic migrations)."""

import os
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.adapters.fake_llm_client import FakeLLMClient
from app.api.deps import get_llm_client
from app.core.config import Settings, get_settings
from app.db.session import get_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[2]

# The compose service name is `db`; from the host it is localhost. CI sets
# DATABASE_URL itself, so only fall back to localhost here.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://radar:radar@localhost:5432/radar")


@pytest.fixture(scope="session")
def test_db_url() -> str:
    return os.environ["DATABASE_URL"]


@pytest.fixture(scope="session")
def apply_migrations(test_db_url: str) -> None:
    assert test_db_url  # silence unused warning while keeping dependency order
    alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")


@pytest.fixture()
def llm_client(request: pytest.FixtureRequest) -> FakeLLMClient | None:
    """Scripted LLM answers, set per test with indirect parametrization.

    Tests pass a list of outcomes via
    ``@pytest.mark.parametrize("llm_client", [[...]], indirect=True)``;
    without it, ``None`` keeps the real client dependency unoverridden.
    """
    outcomes = getattr(request, "param", None)
    return FakeLLMClient(outcomes) if outcomes is not None else None


@pytest.fixture()
async def client(
    apply_migrations: None,
    tmp_path: Path,
    llm_client: FakeLLMClient | None,
) -> AsyncIterator[tuple[AsyncClient, AsyncSession]]:
    """HTTP client backed by the real app, with isolated storage and a clean DB."""
    engine = create_async_engine(os.environ["DATABASE_URL"])
    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE licitacion CASCADE"))

    settings = Settings(storage_dir=str(tmp_path))
    app = create_app()

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with session_maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    app.dependency_overrides[get_settings] = lambda: settings
    if llm_client is not None:
        app.dependency_overrides[get_llm_client] = lambda: llm_client

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http, session_maker

    await engine.dispose()
