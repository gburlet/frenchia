"""Health checks for the native inference services (registered in config.health)."""

from .providers import get_chat_model, get_speech_synth


def check_llm() -> str:
    return "ok" if get_chat_model().health() else "error"


def check_tts() -> str:
    return "ok" if get_speech_synth().health() else "error"
