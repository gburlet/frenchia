"""End-to-end check of the live inference services through the provider layer."""

import time
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from pydantic import BaseModel

from inference.errors import InferenceError
from inference.llm import Message, complete_structured
from inference.providers import get_audio_cache, get_chat_model, get_speech_synth


class Answer(BaseModel):
    answer: str
    explanation: str


class Command(BaseCommand):
    help = "Call the LLM (plain + structured) and TTS through the providers and report timings."

    def handle(self, *args: Any, **options: Any) -> None:
        chat, synth = get_chat_model(), get_speech_synth()
        self.stdout.write(f"LLM {chat.model}: health={'ok' if chat.health() else 'error'}")
        self.stdout.write(
            f"TTS {synth.model} ({synth.voice}): health={'ok' if synth.health() else 'error'}"
        )
        try:
            completion = chat.complete(
                [Message("user", "En un mot : quelle est la capitale du Québec ?")], max_tokens=20
            )
            self.stdout.write(
                f"  plain: {completion.content.strip()!r} ({completion.latency_ms} ms)"
            )
            result, meta = complete_structured(
                chat,
                [Message("user", "Au Québec, que veut dire « magasiner » ? Réponds en anglais.")],
                Answer,
                max_tokens=150,
            )
            self.stdout.write(f"  structured: {result.answer!r} ({meta.latency_ms} ms)")
            started = time.perf_counter()
            clip = get_audio_cache().get_or_create("Salut ! On va-tu souper au resto ?")
            elapsed = round((time.perf_counter() - started) * 1000)
            self.stdout.write(f"  tts: {clip.path.name} cached={clip.cached} ({elapsed} ms)")
        except InferenceError as exc:
            raise CommandError(f"{exc.service}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS("Inference providers OK"))
