from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://radar:radar@db:5432/radar"
    nan_api_key: str | None = None
    nan_base_url: str = "https://api.nan.builders/v1"
    extraction_model: str = "deepseek-v4-flash"


@lru_cache
def get_settings() -> Settings:
    return Settings()
