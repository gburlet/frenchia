"""Provider factory: the only place that knows which runtime backs the LLM and TTS.
Domain code calls get_chat_model() / get_speech_synth() / get_audio_cache()."""

from functools import cache
from pathlib import Path

from django.conf import settings

from .audio import AudioCache
from .fakes import FakeChatModel, FakeSpeechSynth
from .llm import ChatModel, OpenAICompatibleChatModel
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
    for factory in (get_chat_model, get_speech_synth, get_audio_cache):
        factory.cache_clear()
