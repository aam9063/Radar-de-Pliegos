"""FastAPI dependencies for LLM clients and the current date."""

from datetime import date
from typing import Annotated

from fastapi import Depends

from app.adapters.nan_llm_client import NanLLMClient
from app.core.config import Settings, get_settings
from app.domain.llm import LLMClient


def get_llm_client(settings: Annotated[Settings, Depends(get_settings)]) -> LLMClient:
    """LLMClient port wired to the real NaN adapter (overridable in tests)."""
    return NanLLMClient(settings)


def get_hoy() -> date:
    """Current date for the decision engine (overridable to test deterministically)."""
    return date.today()
