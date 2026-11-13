"""Application settings, read from the environment (12-factor).

Local development and ``docker compose`` work with the defaults below. A hosted
deployment (Render) overrides them through environment variables:

- ``DATABASE_URL`` arrives as ``postgresql://…``; the async engine needs the
  ``postgresql+asyncpg://`` scheme, so it is normalised here instead of asking
  every operator to edit the value by hand.
- ``FRONTEND_ORIGINS`` is a comma-separated list of the origins allowed to call
  the API from a browser (CORS). It must be a plain string in the environment,
  so the field opts out of pydantic-settings JSON decoding.
"""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The Vite dev server and preview builds used during local development.
LOCAL_FRONTEND_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]

_SCHEMES_TO_UPGRADE = ("postgres://", "postgresql://")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://radar:radar@db:5432/radar"
    storage_dir: str = "storage"
    frontend_origins: Annotated[list[str], NoDecode] = LOCAL_FRONTEND_ORIGINS
    nan_api_key: str | None = None
    nan_base_url: str = "https://api.nan.builders/v1"
    nan_max_concurrency: int = 5
    nan_max_retries: int = 3
    nan_backoff_base_seconds: float = 0.5
    extraction_model: str = "deepseek-v4-flash"
    summary_model: str = "deepseek-v4-flash"

    @field_validator("database_url")
    @classmethod
    def _normalise_database_url(cls, valor: str) -> str:
        """Accept the plain Postgres URL a host hands over and add the driver."""

        for esquema in _SCHEMES_TO_UPGRADE:
            if valor.startswith(esquema):
                valor = f"postgresql+asyncpg://{valor[len(esquema) :]}"
                break
        # asyncpg takes ``ssl=require``; hosts hand out ``sslmode=require``.
        return valor.replace("sslmode=", "ssl=")

    @field_validator("frontend_origins", mode="before")
    @classmethod
    def _split_origins(cls, valor: object) -> object:
        """Read a comma-separated environment value as a list of origins."""

        if isinstance(valor, str):
            return [origen.strip() for origen in valor.split(",") if origen.strip()]
        return valor


@lru_cache
def get_settings() -> Settings:
    return Settings()
