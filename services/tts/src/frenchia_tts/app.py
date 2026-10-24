"""OpenAI-speech-compatible FastAPI app."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .engine import VOICE_INFO, KokoroEngine, Synthesizer

log = logging.getLogger("frenchia_tts.api")


class SpeechRequest(BaseModel):
    model: str | None = None
    input: str
    voice: str | None = None
    speed: float = Field(1.0, ge=0.5, le=1.5)
    response_format: Literal["wav"] = "wav"


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def _error(status: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}, **extra}, status_code=status)


def create_app(settings: Settings | None = None, synth: Synthesizer | None = None) -> FastAPI:
    cfg = settings or Settings()
    engine: Synthesizer = synth or KokoroEngine(cfg)
    started = time.monotonic()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        task = asyncio.create_task(engine.start())  # /health reports "loading" meanwhile
        yield
        task.cancel()
        engine.close()

    app = FastAPI(title="Frenchia TTS", lifespan=lifespan)

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, e: ApiError) -> JSONResponse:
        return _error(e.status, e.code, e.message)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, e: RequestValidationError) -> JSONResponse:
        msg = "; ".join(f"{'.'.join(map(str, x['loc'][1:]))}: {x['msg']}" for x in e.errors())
        return _error(422, "validation_error", msg)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, e: StarletteHTTPException) -> JSONResponse:
        return _error(e.status_code, "http_error", str(e.detail))

    @app.get("/health")
    async def health() -> JSONResponse:
        body: dict[str, object] = {"status": engine.status, "model": engine.model_name}
        if engine.error:
            body["error"] = engine.error
        if engine.status != "ok":
            return JSONResponse(body, status_code=503)
        active, peak = engine.metal_mb()
        body |= {
            "voices": engine.voices,
            "sample_rate": engine.sample_rate,
            "uptime_s": round(time.monotonic() - started, 1),
            "metal_active_mb": round(active, 1),
            "metal_peak_mb": round(peak, 1),
        }
        return JSONResponse(body)

    @app.get("/v1/audio/voices")
    async def voices() -> dict[str, list[dict[str, str]]]:
        return {
            "voices": [
                {"id": v, "language": VOICE_INFO[v][0], "gender": VOICE_INFO[v][1]}
                for v in engine.voices
                if v in VOICE_INFO
            ]
        }

    @app.post("/v1/audio/speech")
    async def speech(req: SpeechRequest) -> Response:
        text = req.input.strip()
        voice = req.voice or cfg.default_voice
        if not text:
            raise ApiError(422, "validation_error", "input must not be empty")
        if len(text) > cfg.max_chars:
            raise ApiError(413, "input_too_long", f"input exceeds {cfg.max_chars} characters")
        if voice not in engine.voices:
            raise ApiError(422, "unknown_voice", f"unknown voice {voice!r}")
        if engine.status != "ok":
            raise ApiError(503, engine.status, f"engine is {engine.status}")
        try:
            r = await engine.synthesize(text, voice, req.speed)
        except Exception as e:
            log.exception("synthesis failed")
            raise ApiError(500, "synthesis_failed", f"synthesis failed: {e!r}") from e
        log.info(
            "speech chars=%d chunks=%d audio_s=%.2f synth_s=%.2f",
            len(text), r.chunks, r.duration_s, r.synth_s,
        )  # fmt: skip
        return Response(
            r.wav,
            media_type="audio/wav",
            headers={
                "X-Audio-Duration-Seconds": f"{r.duration_s:.3f}",
                "X-Synthesis-Seconds": f"{r.synth_s:.3f}",
                "X-Chunks": str(r.chunks),
            },
        )

    return app
