"""Chat models behind a small protocol, so runtimes and models can be replaced without
touching learning-domain code. The live implementation speaks the OpenAI-compatible
chat completions API (Ollama, llama.cpp server, LM Studio, ...)."""

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from .errors import (
    InferenceError,
    InferenceTimeout,
    InferenceUnavailable,
    InvalidOutput,
)
from .resilience import CircuitBreaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Message:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True)
class Completion:
    content: str
    model: str
    latency_ms: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None


class ChatModel(Protocol):
    model: str

    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> Completion: ...

    def health(self) -> bool: ...


def is_cloud_model(model: str) -> bool:
    """Ollama cloud models are tagged ':cloud' / '-cloud'; Frenchia never uses paid inference."""
    return model.endswith("cloud")


def complete_structured[T: BaseModel](
    chat: ChatModel,
    messages: Sequence[Message],
    schema: type[T],
    *,
    temperature: float = 0.0,
    max_tokens: int = 800,
    retries: int = 1,
) -> tuple[T, Completion]:
    """Request JSON matching `schema` (grammar-constrained where the runtime supports it)
    and validate it. On invalid output, retry with the validation error as feedback."""
    json_schema = schema.model_json_schema()
    attempt_messages = list(messages)
    for attempt in range(retries + 1):
        completion = chat.complete(
            attempt_messages,
            json_schema=json_schema,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        try:
            return schema.model_validate_json(completion.content), completion
        except ValidationError as exc:
            logger.warning("Invalid %s output (attempt %d): %s", schema.__name__, attempt + 1, exc)
            attempt_messages = [
                *messages,
                Message("assistant", completion.content),
                Message("user", f"That output was invalid: {exc}. Reply again with valid JSON."),
            ]
    raise InvalidOutput("llm", f"Model output did not match {schema.__name__}")


class OpenAICompatibleChatModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        timeout_s: float = 120.0,
        extra_body: dict[str, Any] | None = None,
        breaker: CircuitBreaker | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if is_cloud_model(model):
            raise ValueError(f"Cloud model {model!r} is not allowed: inference must stay local")
        self.model = model
        # Ollama extension: no hidden "thinking" tokens for interactive requests.
        self.extra_body = {"reasoning_effort": "none"} if extra_body is None else extra_body
        self.breaker = breaker or CircuitBreaker("llm")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(timeout_s, connect=3.0),
            transport=transport,
        )

    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> Completion:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
            **self.extra_body,
        }
        if json_schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "output", "schema": json_schema, "strict": True},
            }
        started = time.perf_counter()
        data = self._post("chat/completions", body)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise InferenceError("llm", "Malformed chat completion response") from exc
        usage = data.get("usage") or {}
        return Completion(
            content=content,
            model=data.get("model", self.model),
            latency_ms=round((time.perf_counter() - started) * 1000),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
        )

    def health(self) -> bool:
        """True when the server answers and the configured model is available."""
        try:
            response = self._http.get("models", timeout=2.0)
            response.raise_for_status()
            return any(m.get("id") == self.model for m in response.json().get("data", []))
        except (httpx.HTTPError, ValueError):
            return False

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        self.breaker.before_call()
        try:
            response = self._http.post(path, json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self.breaker.record_failure()
            raise InferenceUnavailable("llm", "The language model service is not running") from exc
        except httpx.TimeoutException as exc:
            self.breaker.record_failure()
            raise InferenceTimeout("llm", "The language model took too long to answer") from exc
        self.breaker.record_success()
        if response.status_code == 404:
            raise InferenceUnavailable("llm", f"Model {self.model!r} is not available")
        if response.status_code >= 400:
            raise InferenceError("llm", f"LLM error {response.status_code}: {response.text[:200]}")
        try:
            data: dict[str, Any] = response.json()
        except json.JSONDecodeError as exc:
            raise InferenceError("llm", "LLM returned a non-JSON response") from exc
        return data
