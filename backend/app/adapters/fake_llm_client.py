"""Deterministic in-memory ``LLMClient`` for tests. Never touches the network."""

from collections.abc import Callable, Sequence
from typing import Any

FakeOutcome = dict[str, Any] | Exception

Responder = Callable[[str, str, dict[str, Any]], dict[str, Any]]


class FakeLLMClient:
    """Scripted ``LLMClient`` for unit tests (RP-04 extraction and error paths).

    Outcomes are consumed in order:

    - a ``dict`` is returned as the JSON answer;
    - an ``Exception`` instance is raised, so tests simulate provider faults
      with the domain errors: ``LLMRateLimitError`` (HTTP 429),
      ``LLMServerError`` (HTTP 5xx) or ``LLMInvalidJSONError`` (unparseable
      answer). Retrying/backoff is the caller's concern, not the fake's.

    When the queue runs out, the last outcome repeats. Alternatively pass a
    ``responder`` callable ``(model, prompt, schema) -> dict`` for dynamic
    answers. Every call is recorded in ``calls`` in order.
    """

    def __init__(
        self,
        outcomes: Sequence[FakeOutcome] | None = None,
        *,
        responder: Responder | None = None,
    ) -> None:
        if not outcomes and responder is None:
            raise ValueError("FakeLLMClient needs scripted outcomes or a responder")
        self._outcomes = list(outcomes) if outcomes is not None else []
        self._responder = responder
        self._cursor = 0
        self.calls: list[dict[str, Any]] = []

    async def complete_json(
        self, *, model: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({"model": model, "prompt": prompt, "schema": schema})
        if self._responder is not None:
            return self._responder(model, prompt, schema)
        outcome = self._outcomes[min(self._cursor, len(self._outcomes) - 1)]
        self._cursor += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
