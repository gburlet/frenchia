import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from inference.errors import InferenceTimeout, InferenceUnavailable, InvalidOutput
from inference.fakes import FakeChatModel
from inference.llm import Message, OpenAICompatibleChatModel, complete_structured
from inference.resilience import CircuitBreaker

Handler = Callable[[httpx.Request], httpx.Response]


def chat_model(handler: Handler, **kwargs: object) -> OpenAICompatibleChatModel:
    return OpenAICompatibleChatModel(
        "http://llm.test/v1",
        "gemma4:12b",
        transport=httpx.MockTransport(handler),
        **kwargs,  # type: ignore[arg-type]
    )


def ok_response(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": "gemma4:12b",
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 3},
        },
    )


class Verdict(BaseModel):
    verdict: str
    score: int


def test_complete_sends_openai_request_with_schema_and_thinking_off() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return ok_response("Bonjour")

    completion = chat_model(handler).complete(
        [Message("user", "Salut")], json_schema={"type": "object"}, max_tokens=50
    )
    body = seen["body"]
    assert isinstance(body, dict)
    assert seen["path"] == "/v1/chat/completions"
    assert body["model"] == "gemma4:12b"
    assert body["reasoning_effort"] == "none"
    assert body["response_format"]["json_schema"]["schema"] == {"type": "object"}
    assert completion.content == "Bonjour"
    assert completion.completion_tokens == 3


def test_connection_error_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(InferenceUnavailable):
        chat_model(handler).complete([Message("user", "x")])


def test_read_timeout_maps_to_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("slow")

    with pytest.raises(InferenceTimeout):
        chat_model(handler).complete([Message("user", "x")])


def test_missing_model_maps_to_unavailable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(InferenceUnavailable, match="not available"):
        chat_model(handler).complete([Message("user", "x")])


def test_circuit_opens_after_repeated_connection_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("refused")

    model = chat_model(handler, breaker=CircuitBreaker("llm", failure_threshold=2))
    for _ in range(4):
        with pytest.raises(InferenceUnavailable):
            model.complete([Message("user", "x")])
    assert calls == 2  # later calls fail fast without touching the network


def test_cloud_models_are_rejected() -> None:
    with pytest.raises(ValueError, match="local"):
        OpenAICompatibleChatModel("http://llm.test/v1", "gpt-oss:120b-cloud")


def test_health_requires_configured_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "qwen3.5:9b"}]})

    assert chat_model(handler).health() is False


def test_complete_structured_validates_and_retries_once() -> None:
    replies = iter(['{"verdict": "correct"}', '{"verdict": "correct", "score": 90}'])
    fake = FakeChatModel(responder=lambda messages: next(replies))
    result, _ = complete_structured(fake, [Message("user", "Évalue")], Verdict)
    assert result == Verdict(verdict="correct", score=90)
    assert len(fake.calls) == 2
    assert "invalid" in fake.calls[1]["messages"][-1].content


def test_complete_structured_gives_up_with_invalid_output() -> None:
    fake = FakeChatModel(responder=lambda messages: "not json")
    with pytest.raises(InvalidOutput):
        complete_structured(fake, [Message("user", "x")], Verdict, retries=1)


def test_fake_chat_model_produces_schema_shaped_json() -> None:
    result, _ = complete_structured(FakeChatModel(), [Message("user", "x")], Verdict)
    assert result == Verdict(verdict="test", score=0)


def test_remote_author_sends_key_reasoning_budget_and_waits_for_a_waking_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr("inference.llm.time.sleep", sleeps.append)
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(503, headers={"Retry-After": "20"}, text="model_scaled_to_zero")
        return ok_response("{}")

    chat = chat_model(
        handler,
        api_key="secret",
        extra_body={"reasoning_effort": "low"},
        reasoning_tokens=4000,
        wake_wait_s=240.0,
    )
    chat.complete([Message("user", "hi")], max_tokens=800)
    body = json.loads(seen[-1].content)
    assert seen[-1].headers["authorization"] == "Bearer secret"
    assert body["max_tokens"] == 4800 and body["reasoning_effort"] == "low"
    assert sleeps == [20.0]


def test_a_503_without_wake_wait_is_unavailable() -> None:
    chat = chat_model(lambda r: httpx.Response(503, text="insufficient_capacity"))
    with pytest.raises(InferenceUnavailable):
        chat.complete([Message("user", "hi")])


def test_authoring_model_is_local_unless_configured_remote(settings: Any) -> None:
    from inference.providers import get_authoring_chat_model, get_chat_model, reset_providers

    settings.INFERENCE = {**settings.INFERENCE, "MODE": "live"}
    reset_providers()
    assert get_authoring_chat_model() is get_chat_model()
    settings.AUTHORING = {
        **settings.AUTHORING,
        "LLM": "remote",
        "BASE_URL": "https://inference.example/v1",
        "API_KEY": "k",
    }
    reset_providers()
    remote = get_authoring_chat_model()
    assert remote is not get_chat_model() and remote.model == "gpt-oss-120b"
