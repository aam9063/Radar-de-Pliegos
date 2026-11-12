"""LLM client port: pure interface between domain services and AI providers.

This module must stay free of FastAPI, SQLAlchemy and AI SDK imports
(architecture rule, AGENTS.md section 8): it is pure Python typing only.
"""

from typing import Any, Protocol, runtime_checkable


class LLMError(Exception):
    """Base class for errors raised by LLM clients."""


class LLMRateLimitError(LLMError):
    """The provider kept answering HTTP 429 after bounded retries."""


class LLMServerError(LLMError):
    """The provider kept answering HTTP 5xx after bounded retries."""


class LLMInvalidJSONError(LLMError):
    """The model answer could not be parsed as a JSON object."""


@runtime_checkable
class LLMClient(Protocol):
    """Port used by extraction services (RP-04) to reach the AI provider.

    Implementations: ``NanLLMClient`` (real NaN Builders API) and
    ``FakeLLMClient`` (deterministic tests). No test ever calls the real API.
    """

    async def complete_json(
        self, *, model: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Run a chat completion constrained by ``schema`` and return the JSON object.

        The answer must be a JSON object (``dict``), never an array or scalar.
        Implementations must raise, without retrying further:

        - ``LLMRateLimitError`` when HTTP 429 retries are exhausted.
        - ``LLMServerError`` when HTTP 5xx retries are exhausted.
        - ``LLMInvalidJSONError`` when the answer is not a JSON object.

        Retrying on invalid JSON is the caller's (extractor's) decision.
        """
