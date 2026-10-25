"""Deterministic stand-ins for the native services (INFERENCE_MODE=fake): used by tests,
end-to-end runs and development without the LLM/TTS running."""

import io
import json
import struct
import wave
from collections.abc import AsyncIterator, Callable, Sequence
from typing import Any

from .llm import Completion, Message


class FakeChatModel:
    model = "fake-llm"

    def __init__(self, responder: Callable[[Sequence[Message]], str] | None = None) -> None:
        self.responder = responder
        self.calls: list[dict[str, Any]] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> Completion:
        self.calls.append({"messages": list(messages), "json_schema": json_schema})
        if self.responder is not None:
            content = self.responder(messages)
        elif json_schema is not None:
            content = json.dumps(_example_for(json_schema))
        else:
            content = "Ceci est une réponse de test."
        return Completion(content=content, model=self.model, latency_ms=1)

    async def stream(
        self, messages: Sequence[Message], *, temperature: float = 0.3, max_tokens: int = 800
    ) -> AsyncIterator[str]:
        self.calls.append({"messages": list(messages), "json_schema": None, "stream": True})
        text = self.responder(messages) if self.responder else "Voici une réponse de test."
        for word in text.split(" "):
            yield word + " "

    def warm(self) -> None:
        self.calls.append({"warm": True})

    def health(self) -> bool:
        return True


def _example_for(schema: dict[str, Any], defs: dict[str, Any] | None = None) -> Any:
    """A minimal instance satisfying a (pydantic-generated) JSON schema."""
    defs = defs if defs is not None else schema.get("$defs", {})
    if "$ref" in schema:
        return _example_for(defs[schema["$ref"].split("/")[-1]], defs)
    if "enum" in schema:
        return schema["enum"][0]
    if "anyOf" in schema:
        return _example_for(schema["anyOf"][0], defs)
    kind = schema.get("type")
    if kind == "object":
        return {k: _example_for(v, defs) for k, v in schema.get("properties", {}).items()}
    if kind == "array":
        return []
    return {"string": "test", "integer": 0, "number": 0.0, "boolean": False}.get(str(kind))


class FakeSpeechSynth:
    model = "fake-tts"
    voice = "fake"

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def synthesize(self, text: str, *, speed: float = 1.0) -> bytes:
        self.calls.append((text, speed))
        return silent_wav(seconds=0.1)

    def health(self) -> bool:
        return True


def silent_wav(seconds: float, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(struct.pack("<h", 0) * int(seconds * sample_rate))
    return buf.getvalue()
