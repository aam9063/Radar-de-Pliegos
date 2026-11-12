"""NaN Builders adapter for the ``LLMClient`` port.

Calls ``/chat/completions`` with a ``json_schema`` response format and **no**
tools (NaN contract for ``deepseek-v4-flash``, AGENTS.md section 2). Enforces a
semaphore of concurrent requests (default 5) and retries HTTP 429 / 5xx with
exponential backoff + jitter. Logs model, tokens, latency and request id —
never the prompt text nor the API key.
"""

import asyncio
import json
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import Any

from openai import APIStatusError, AsyncOpenAI
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.shared_params import ResponseFormatJSONSchema
from openai.types.shared_params.response_format_json_schema import JSONSchema

from app.core.config import Settings
from app.domain.llm import LLMInvalidJSONError, LLMRateLimitError, LLMServerError

logger = logging.getLogger(__name__)

SleepFunc = Callable[[float], Awaitable[None]]

_RATE_LIMIT_STATUS = 429


class NanLLMClient:
    """``LLMClient`` backed by the NaN Builders OpenAI-compatible API.

    ``client`` and ``sleep`` are injection points for tests: a stub transport
    and a fake clock let the unit suite verify retries, backoff and the
    concurrency cap without network access and without real sleeping.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        client: AsyncOpenAI | None = None,
        sleep: SleepFunc | None = None,
    ) -> None:
        self._client = client or AsyncOpenAI(
            base_url=settings.nan_base_url,
            api_key=settings.nan_api_key or "",
        )
        self._sleep = sleep or asyncio.sleep
        self._semaphore = asyncio.Semaphore(settings.nan_max_concurrency)
        self._max_retries = settings.nan_max_retries
        self._backoff_base = settings.nan_backoff_base_seconds

    async def complete_json(
        self, *, model: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Run one JSON-schema chat completion, holding a concurrency slot."""
        async with self._semaphore:
            return await self._complete_with_retries(model=model, prompt=prompt, schema=schema)

    async def _complete_with_retries(
        self, *, model: str, prompt: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        messages: list[ChatCompletionMessageParam] = [{"role": "user", "content": prompt}]
        attempt = 0
        while True:
            started = time.perf_counter()
            try:
                completion = await self._client.chat.completions.create(
                    model=model,
                    messages=messages,
                    response_format=self._response_format(schema),
                )
            except APIStatusError as exc:
                latency_ms = round((time.perf_counter() - started) * 1000)
                error_class, status = self._classify(exc)
                if error_class is None:
                    raise
                if attempt >= self._max_retries:
                    raise error_class(
                        f"NaN API answered HTTP {status} on every attempt ({attempt + 1} total)"
                    ) from exc
                delay = self._backoff_delay(attempt)
                logger.warning(
                    "nan llm retry attempt=%d status=%d latency_ms=%d delay_ms=%d",
                    attempt + 1,
                    status,
                    latency_ms,
                    round(delay * 1000),
                )
                await self._sleep(delay)
                attempt += 1
            else:
                return self._parse_completion(
                    completion, fallback_model=model, elapsed=time.perf_counter() - started
                )

    @staticmethod
    def _classify(exc: APIStatusError) -> tuple[type[Exception] | None, int]:
        status = exc.status_code
        if status == _RATE_LIMIT_STATUS:
            return LLMRateLimitError, status
        if 500 <= status < 600:
            return LLMServerError, status
        return None, status

    def _backoff_delay(self, attempt: int) -> float:
        return self._backoff_base * (2.0**attempt) * random.uniform(0.5, 1.5)

    @staticmethod
    def _response_format(schema: dict[str, Any]) -> ResponseFormatJSONSchema:
        json_schema: JSONSchema = {"name": "response", "strict": True, "schema": schema}
        return {"type": "json_schema", "json_schema": json_schema}

    def _parse_completion(
        self, completion: ChatCompletion, *, fallback_model: str, elapsed: float
    ) -> dict[str, Any]:
        content = completion.choices[0].message.content
        if content is None:
            raise LLMInvalidJSONError("model returned an empty answer")
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMInvalidJSONError(f"model answer is not valid JSON: {exc.msg}") from exc
        if not isinstance(parsed, dict):
            raise LLMInvalidJSONError("model answer is not a JSON object")
        usage = completion.usage
        tokens = (
            f"prompt_tokens={usage.prompt_tokens} "
            f"completion_tokens={usage.completion_tokens} "
            f"total_tokens={usage.total_tokens}"
            if usage
            else "tokens=unavailable"
        )
        logger.info(
            "nan llm ok model=%s request_id=%s latency_ms=%d %s",
            completion.model or fallback_model,
            completion.id,
            round(elapsed * 1000),
            tokens,
        )
        return parsed
