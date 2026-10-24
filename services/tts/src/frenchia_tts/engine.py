"""Kokoro/MLX engine. All MLX work runs on ONE dedicated thread (MLX streams are per-thread)."""

from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np

from .chunker import chunk_text
from .config import Settings

log = logging.getLogger("frenchia_tts.engine")
SAMPLE_RATE = 24000
# voice id -> (BCP-47-ish language, gender)
VOICE_INFO = {"ff_siwis": ("fr-fr", "female")}
MB = 1024 * 1024


@dataclass(frozen=True)
class Synthesis:
    wav: bytes
    duration_s: float
    synth_s: float
    chunks: int


class Synthesizer(Protocol):
    model_name: str
    sample_rate: int
    voices: list[str]
    status: str  # "loading" | "ok" | "error"
    error: str | None

    async def start(self) -> None: ...
    async def synthesize(self, text: str, voice: str, speed: float) -> Synthesis: ...
    def metal_mb(self) -> tuple[float, float]: ...
    def close(self) -> None: ...


def to_wav(audio: np.ndarray[Any, Any], sample_rate: int = SAMPLE_RATE) -> bytes:
    """Float samples in [-1, 1] -> PCM16 mono WAV bytes."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


class KokoroEngine:
    sample_rate = SAMPLE_RATE

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.model_name = settings.model
        self.voices = list(VOICE_INFO)
        self.status = "loading"
        self.error: str | None = None
        self._model: Any = None
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="mlx")

    async def start(self) -> None:
        try:
            await asyncio.get_running_loop().run_in_executor(self._pool, self._load)
            self.status = "ok"
        except Exception as e:
            log.exception("model load failed")
            self.status, self.error = "error", repr(e)

    def _load(self) -> None:  # runs on the MLX worker thread
        import mlx.core as mx
        from mlx_audio.tts.utils import load_model

        if self.s.mlx_cache_limit_mb is not None:
            mx.set_cache_limit(self.s.mlx_cache_limit_mb * MB)
        t = time.perf_counter()
        self._model = load_model(self.s.model)
        log.info("model %s loaded in %.2fs", self.s.model, time.perf_counter() - t)
        t = time.perf_counter()
        self._synth("Bonjour, ça va ?", self.s.default_voice, 1.0)
        log.info("warm-up synthesis took %.2fs", time.perf_counter() - t)

    def _synth(self, text: str, voice: str, speed: float) -> Synthesis:  # worker thread
        t = time.perf_counter()
        chunks = chunk_text(text)
        gap = np.zeros(self.sample_rate * self.s.sentence_pause_ms // 1000, dtype=np.float32)
        parts: list[np.ndarray[Any, Any]] = []
        for i, chunk in enumerate(chunks):
            if i:
                parts.append(gap)
            for r in self._model.generate(
                text=chunk, voice=voice, speed=speed, lang_code=self.s.lang_code
            ):
                parts.append(np.array(r.audio, dtype=np.float32).reshape(-1))
        audio = np.concatenate(parts) if parts else np.zeros(0, dtype=np.float32)
        return Synthesis(
            to_wav(audio), len(audio) / self.sample_rate, time.perf_counter() - t, len(chunks)
        )

    async def synthesize(self, text: str, voice: str, speed: float) -> Synthesis:
        return await asyncio.get_running_loop().run_in_executor(
            self._pool, self._synth, text, voice, speed
        )

    def metal_mb(self) -> tuple[float, float]:
        import mlx.core as mx

        return mx.get_active_memory() / MB, mx.get_peak_memory() / MB

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
