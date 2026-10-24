"""Errors raised by inference providers. Learning-domain code catches these, never httpx."""


class InferenceError(Exception):
    """A provider call failed. `service` is "llm" or "tts"."""

    def __init__(self, service: str, message: str) -> None:
        super().__init__(message)
        self.service = service


class InferenceUnavailable(InferenceError):
    """The service is down, unreachable, or temporarily disabled by the circuit breaker."""


class InferenceTimeout(InferenceError):
    """The service accepted the request but did not answer in time."""


class InvalidOutput(InferenceError):
    """The model's output did not match the requested schema."""


class InvalidRequest(InferenceError):
    """The service rejected the input (e.g. text too long for TTS)."""
