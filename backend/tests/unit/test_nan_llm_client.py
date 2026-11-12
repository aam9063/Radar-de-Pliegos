"""Unit tests for NanLLMClient: request shape, AC-10 limits, logging discipline.

The transport (AsyncOpenAI chat completions) and the sleep clock are stubbed,
so no test touches the network and no test really sleeps.
"""

import asyncio
import logging
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
from openai import APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice
from openai.types.completion_usage import CompletionUsage

from app.adapters.nan_llm_client import NanLLMClient
from app.core.config import Settings
from app.domain.llm import LLMClient, LLMInvalidJSONError, LLMRateLimitError, LLMServerError

BASE_URL = "https://api.nan.builders/v1"
API_KEY = "nan-secret-key"
PROMPT = "SECRET-PROMPT extrae los datos del pliego"
SCHEMA = {
    "type": "object",
    "title": "respuesta",
    "properties": {"ok": {"type": "boolean"}},
}


class StubTransport:
    """Fake for the AsyncOpenAI chat completions transport.

    Plays ``outcomes`` in order; when exhausted the last outcome repeats.
    ``ChatCompletion`` outcomes are returned, ``APIStatusError`` ones are raised.
    """

    def __init__(self, outcomes: list[ChatCompletion | APIStatusError]) -> None:
        self._outcomes = outcomes
        self._cursor = 0
        self.calls: list[dict[str, Any]] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def create(self, **kwargs: Any) -> ChatCompletion:
        self.calls.append(kwargs)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)  # cooperative yield only: no real waiting
            outcome = self._outcomes[min(self._cursor, len(self._outcomes) - 1)]
            self._cursor += 1
            if isinstance(outcome, APIStatusError):
                raise outcome
            return outcome
        finally:
            self.in_flight -= 1


class FakeClock:
    """Replaces real sleeping: records requested backoff delays."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


def _settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "nan_api_key": API_KEY,
        "nan_base_url": BASE_URL,
        "nan_max_concurrency": 5,
        "nan_max_retries": 2,
        "nan_backoff_base_seconds": 0.5,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def _make_client(transport: StubTransport, clock: FakeClock, settings: Settings) -> NanLLMClient:
    # wrap the stub in the chat.completions attribute path the adapter walks,
    # then cast: it duck-types the AsyncOpenAI surface the adapter uses
    sdk_like = SimpleNamespace(chat=SimpleNamespace(completions=transport))
    return NanLLMClient(settings, client=cast("AsyncOpenAI", sdk_like), sleep=clock.sleep)


def _api_status_error(status: int) -> APIStatusError:
    request = httpx.Request("POST", f"{BASE_URL}/chat/completions")
    response = httpx.Response(status, request=request)
    return APIStatusError(f"HTTP {status}", response=response, body=None)


def _completion(content: str = '{"ok": true}', request_id: str = "cmpl-test-1") -> ChatCompletion:
    return ChatCompletion.model_construct(
        id=request_id,
        choices=[
            Choice.model_construct(
                finish_reason="stop",
                index=0,
                message=ChatCompletionMessage.model_construct(content=content),
            )
        ],
        created=0,
        model="deepseek-v4-flash",
        object="chat.completion",
        usage=CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


# --- Request shape: json_schema, never tools ---------------------------------


async def test_sends_json_schema_response_format_without_tools() -> None:
    transport = StubTransport([_completion()])
    client = _make_client(transport, FakeClock(), _settings())

    result = await client.complete_json(model="deepseek-v4-flash", prompt=PROMPT, schema=SCHEMA)

    assert result == {"ok": True}
    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call["model"] == "deepseek-v4-flash"
    assert call["messages"] == [{"role": "user", "content": PROMPT}]
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["schema"] == SCHEMA
    assert call["response_format"]["json_schema"]["strict"] is True
    assert "tools" not in call
    assert "tool_choice" not in call


# --- AC-10: bounded retries with exponential backoff on 429 / 5xx ------------


async def test_ac10_retries_429_with_exponential_backoff_then_succeeds() -> None:
    transport = StubTransport([_api_status_error(429), _api_status_error(429), _completion()])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings(nan_backoff_base_seconds=0.4))

    result = await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert result == {"ok": True}
    assert len(transport.calls) == 3
    assert len(clock.delays) == 2
    first, second = clock.delays
    assert 0.4 * 0.5 <= first <= 0.4 * 1.5  # base * 2**0, jittered 0.5x-1.5x
    assert 0.4 * 2 * 0.5 <= second <= 0.4 * 2 * 1.5  # base * 2**1, jittered
    # (no strict ordering: with jitter a doubled base can still draw a smaller delay)


async def test_retries_5xx_with_exponential_backoff_then_succeeds() -> None:
    transport = StubTransport([_api_status_error(503), _api_status_error(502), _completion()])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings(nan_backoff_base_seconds=0.3))

    result = await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert result == {"ok": True}
    assert len(transport.calls) == 3
    first, second = clock.delays
    assert 0.3 * 0.5 <= first <= 0.3 * 1.5
    assert 0.3 * 2 * 0.5 <= second <= 0.3 * 2 * 1.5


async def test_raises_rate_limit_error_after_bounded_retries() -> None:
    transport = StubTransport([_api_status_error(429)])  # repeats forever
    clock = FakeClock()
    client = _make_client(transport, clock, _settings(nan_max_retries=2))

    with pytest.raises(LLMRateLimitError):
        await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert len(transport.calls) == 3  # initial attempt + 2 retries
    assert len(clock.delays) == 2


async def test_raises_server_error_after_bounded_retries() -> None:
    transport = StubTransport([_api_status_error(500)])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings(nan_max_retries=1))

    with pytest.raises(LLMServerError):
        await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert len(transport.calls) == 2  # initial attempt + 1 retry
    assert len(clock.delays) == 1


async def test_does_not_retry_other_status_codes() -> None:
    transport = StubTransport([_api_status_error(400)])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings())

    with pytest.raises(APIStatusError):
        await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert len(transport.calls) == 1
    assert clock.delays == []


# --- AC-10: never more than 5 concurrent requests -----------------------------


async def test_ac10_concurrency_never_exceeds_five() -> None:
    transport = StubTransport([_completion()])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings(nan_max_concurrency=5))

    results = await asyncio.gather(
        *(client.complete_json(model="m", prompt=f"p{i}", schema=SCHEMA) for i in range(10))
    )

    assert len(results) == 10
    assert transport.max_in_flight == 5


# --- Invalid JSON -------------------------------------------------------------


async def test_raises_invalid_json_when_answer_is_not_json() -> None:
    transport = StubTransport([_completion(content="lorem ipsum, no json here")])
    clock = FakeClock()
    client = _make_client(transport, clock, _settings())

    with pytest.raises(LLMInvalidJSONError):
        await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)

    assert len(transport.calls) == 1  # no retry here: RP-04 owns that retry
    assert clock.delays == []


async def test_raises_invalid_json_when_answer_is_not_an_object() -> None:
    transport = StubTransport([_completion(content="[1, 2, 3]")])
    client = _make_client(transport, FakeClock(), _settings())

    with pytest.raises(LLMInvalidJSONError):
        await client.complete_json(model="m", prompt=PROMPT, schema=SCHEMA)


# --- Logging: metadata yes, prompt and key never ------------------------------


async def test_logs_metadata_but_never_prompt_or_key() -> None:
    logger = logging.getLogger("app.adapters.nan_llm_client")
    was_disabled, previous_level = logger.disabled, logger.level
    records: list[logging.LogRecord] = []

    class RecordCapture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = RecordCapture()
    logger.addHandler(handler)
    logger.disabled = False  # alembic's fileConfig disables pre-existing loggers
    logger.setLevel(logging.INFO)
    try:
        transport = StubTransport([_completion(request_id="cmpl-abc-123")])
        client = _make_client(transport, FakeClock(), _settings())
        await client.complete_json(model="deepseek-v4-flash", prompt=PROMPT, schema=SCHEMA)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
        logger.disabled = was_disabled

    text = " ".join(record.getMessage() for record in records)
    assert "deepseek-v4-flash" in text
    assert "cmpl-abc-123" in text
    assert "total_tokens=15" in text
    assert "SECRET-PROMPT" not in text
    assert API_KEY not in text


# --- Construction and port conformance ----------------------------------------


def test_builds_openai_client_from_settings() -> None:
    client = NanLLMClient(_settings())

    # unit-level check of the wiring: the SDK client must come from settings
    assert str(client._client.base_url).rstrip("/") == BASE_URL
    assert client._client.api_key == API_KEY


def test_fulfills_llm_client_port() -> None:
    assert isinstance(NanLLMClient(_settings()), LLMClient)
