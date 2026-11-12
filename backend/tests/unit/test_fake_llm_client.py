"""Unit tests for the deterministic FakeLLMClient (RP-03, AC-10 support)."""

import pytest

from app.adapters.fake_llm_client import FakeLLMClient
from app.domain.llm import (
    LLMClient,
    LLMInvalidJSONError,
    LLMRateLimitError,
    LLMServerError,
)

SCHEMA = {"type": "object", "title": "ficha", "properties": {}}


async def test_returns_scripted_payloads_in_order() -> None:
    fake = FakeLLMClient([{"campo": "a"}, {"campo": "b"}])

    assert await fake.complete_json(model="m", prompt="p1", schema=SCHEMA) == {"campo": "a"}
    assert await fake.complete_json(model="m", prompt="p2", schema=SCHEMA) == {"campo": "b"}
    assert fake.calls == [
        {"model": "m", "prompt": "p1", "schema": SCHEMA},
        {"model": "m", "prompt": "p2", "schema": SCHEMA},
    ]


async def test_repeats_last_outcome_when_queue_is_exhausted() -> None:
    fake = FakeLLMClient([{"n": 1}])

    for _ in range(3):
        assert await fake.complete_json(model="m", prompt="p", schema=SCHEMA) == {"n": 1}
    assert len(fake.calls) == 3


async def test_raises_scripted_domain_errors_in_order() -> None:
    fake = FakeLLMClient(
        [
            LLMRateLimitError("429"),
            LLMServerError("503"),
            LLMInvalidJSONError("answer is not valid JSON"),
            {"ok": True},
        ]
    )

    with pytest.raises(LLMRateLimitError):
        await fake.complete_json(model="m", prompt="p", schema=SCHEMA)
    with pytest.raises(LLMServerError):
        await fake.complete_json(model="m", prompt="p", schema=SCHEMA)
    with pytest.raises(LLMInvalidJSONError):
        await fake.complete_json(model="m", prompt="p", schema=SCHEMA)
    assert await fake.complete_json(model="m", prompt="p", schema=SCHEMA) == {"ok": True}
    assert len(fake.calls) == 4


async def test_responder_mode_answers_from_callable() -> None:
    def responder(model: str, prompt: str, schema: dict) -> dict:
        return {"echo": prompt, "model": model}

    fake = FakeLLMClient(responder=responder)

    result = await fake.complete_json(model="deepseek-v4-flash", prompt="hola", schema=SCHEMA)

    assert result == {"echo": "hola", "model": "deepseek-v4-flash"}
    assert len(fake.calls) == 1


def test_requires_outcomes_or_responder() -> None:
    with pytest.raises(ValueError, match="outcomes or a responder"):
        FakeLLMClient()


def test_fulfills_llm_client_port() -> None:
    assert isinstance(FakeLLMClient([{"ok": True}]), LLMClient)
