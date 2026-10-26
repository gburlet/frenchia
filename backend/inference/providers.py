"""Provider factory: the only place that knows which runtime backs the LLM and TTS.
Domain code calls get_chat_model() / get_speech_synth() / get_audio_cache(), and
get_authoring_chat_model() for content generation."""

from functools import cache
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .audio import AudioCache
from .fakes import FakeChatModel, FakeSpeechSynth
from .llm import ChatModel, OpenAICompatibleChatModel
from .resilience import CircuitBreaker
from .tts import HttpSpeechSynth, SpeechSynth


def _fake() -> bool:
    return bool(settings.INFERENCE["MODE"] == "fake")


@cache
def get_chat_model() -> ChatModel:
    if _fake():
        return FakeChatModel()
    cfg = settings.INFERENCE
    return OpenAICompatibleChatModel(
        cfg["LLM_BASE_URL"], cfg["LLM_MODEL"], timeout_s=cfg["LLM_TIMEOUT_S"]
    )


@cache
def get_authoring_chat_model() -> ChatModel:
    """The LLM that writes learning content: the local one, or a remote OpenAI-compatible
    server (settings.AUTHORING). Learner-facing calls (grading, tutor) never use it."""
    cfg = settings.AUTHORING
    if _fake() or cfg["LLM"] != "remote":
        return get_chat_model()
    if not (cfg["BASE_URL"] and cfg["API_KEY"]):
        raise ImproperlyConfigured("AUTHORING_LLM=remote needs AUTHORING_LLM_BASE_URL and _API_KEY")
    return OpenAICompatibleChatModel(
        cfg["BASE_URL"],
        cfg["MODEL"],
        timeout_s=cfg["TIMEOUT_S"],
        api_key=cfg["API_KEY"],
        extra_body={"reasoning_effort": cfg["REASONING_EFFORT"]},
        reasoning_tokens=cfg["REASONING_TOKENS"],
        wake_wait_s=240.0,
        breaker=CircuitBreaker("authoring-llm"),
    )


@cache
def get_speech_synth() -> SpeechSynth:
    if _fake():
        return FakeSpeechSynth()
    cfg = settings.INFERENCE
    return HttpSpeechSynth(
        cfg["TTS_BASE_URL"],
        model=cfg["TTS_MODEL"],
        voice=cfg["TTS_VOICE"],
        timeout_s=cfg["TTS_TIMEOUT_S"],
    )


@cache
def get_audio_cache() -> AudioCache:
    return AudioCache(Path(settings.AUDIO_CACHE_DIR), get_speech_synth())


def reset_providers() -> None:
    """Forget cached providers (tests, or after settings change)."""
    for factory in (get_chat_model, get_authoring_chat_model, get_speech_synth, get_audio_cache):
        factory.cache_clear()
