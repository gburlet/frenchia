"""Speech synthesis behind a small protocol. The live implementation calls Frenchia's
Kokoro MLX service through its OpenAI-style /v1/audio/speech endpoint."""

from typing import Protocol

import httpx

from .errors import InferenceError, InferenceTimeout, InferenceUnavailable, InvalidRequest
from .resilience import CircuitBreaker


class SpeechSynth(Protocol):
    model: str
    voice: str

    def synthesize(self, text: str, *, speed: float = 1.0) -> bytes:
        """Return WAV bytes."""
        ...

    def health(self) -> bool: ...


class HttpSpeechSynth:
    def __init__(
        self,
        base_url: str,
        *,
        model: str,
        voice: str,
        timeout_s: float = 60.0,
        breaker: CircuitBreaker | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model
        self.voice = voice
        self.breaker = breaker or CircuitBreaker("tts")
        self._http = httpx.Client(
            base_url=base_url.rstrip("/") + "/",
            timeout=httpx.Timeout(timeout_s, connect=3.0),
            transport=transport,
        )

    def synthesize(self, text: str, *, speed: float = 1.0) -> bytes:
        body = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "speed": speed,
            "response_format": "wav",
        }
        self.breaker.before_call()
        try:
            response = self._http.post("v1/audio/speech", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            self.breaker.record_failure()
            raise InferenceUnavailable("tts", "The speech service is not running") from exc
        except httpx.TimeoutException as exc:
            self.breaker.record_failure()
            raise InferenceTimeout("tts", "Speech synthesis took too long") from exc
        self.breaker.record_success()
        if response.status_code == 503:
            raise InferenceUnavailable("tts", "The speech service is still loading")
        if response.status_code in (413, 422):
            raise InvalidRequest("tts", _error_message(response))
        if response.status_code >= 400:
            raise InferenceError(
                "tts", f"TTS error {response.status_code}: {_error_message(response)}"
            )
        return response.content

    def health(self) -> bool:
        try:
            response = self._http.get("health", timeout=2.0)
            return response.status_code == 200 and response.json().get("status") == "ok"
        except (httpx.HTTPError, ValueError):
            return False


def _error_message(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"]["message"])
    except (ValueError, KeyError, TypeError):
        return response.text[:200]
