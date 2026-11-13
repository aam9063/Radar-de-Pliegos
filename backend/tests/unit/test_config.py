"""Settings must come from the environment so the app can run on Render (S3).

Two values decide whether a deploy boots at all: the connection string Render
hands over uses the plain ``postgresql://`` scheme while the async engine needs
``postgresql+asyncpg://``, and the frontend origin is a public URL that does not
exist locally.
"""

import pytest

from app.core.config import Settings, get_settings


def test_database_url_with_postgresql_scheme_is_upgraded_to_asyncpg() -> None:
    settings = Settings(database_url="postgresql://radar:s3cret@db.example.com:5432/radar")

    assert settings.database_url == "postgresql+asyncpg://radar:s3cret@db.example.com:5432/radar"


def test_database_url_with_postgres_scheme_is_upgraded_to_asyncpg() -> None:
    # Render and Heroku hand out the legacy ``postgres://`` alias.
    settings = Settings(database_url="postgres://radar:s3cret@internal:5432/radar")

    assert settings.database_url == "postgresql+asyncpg://radar:s3cret@internal:5432/radar"


def test_database_url_keeps_an_existing_asyncpg_prefix() -> None:
    url = "postgresql+asyncpg://radar:radar@db:5432/radar"

    assert Settings(database_url=url).database_url == url


def test_database_url_translates_sslmode_for_asyncpg() -> None:
    """asyncpg rejects ``sslmode``; hosted Postgres URLs usually carry it."""

    settings = Settings(
        database_url="postgresql://radar:pw@db.example.com:5432/radar?sslmode=require"
    )

    assert settings.database_url == (
        "postgresql+asyncpg://radar:pw@db.example.com:5432/radar?ssl=require"
    )


def test_frontend_origins_default_to_the_local_dev_server() -> None:
    origenes = Settings().frontend_origins

    assert "http://localhost:5173" in origenes


def test_frontend_origins_accept_a_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "FRONTEND_ORIGINS",
        "https://radar-web.onrender.com , https://radar.example.com ",
    )

    origenes = Settings().frontend_origins

    assert origenes == ["https://radar-web.onrender.com", "https://radar.example.com"]


def test_applies_the_configured_origin_to_cors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "https://radar-web.onrender.com")
    get_settings.cache_clear()

    from app.main import create_app

    app = create_app()
    cors = next(
        middleware
        for middleware in app.user_middleware
        if middleware.cls.__name__ == "CORSMiddleware"
    )

    assert "https://radar-web.onrender.com" in cors.kwargs["allow_origins"]
    get_settings.cache_clear()
