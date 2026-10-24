# frenchia-tts

Native (Apple Silicon, MLX/Metal) text-to-speech HTTP service for Frenchia, built on
Kokoro-82M (`mlx-community/Kokoro-82M-bf16`) through `mlx-audio`. It exposes an
OpenAI-speech-compatible API so the engine can be swapped later. Local only: no STT, websockets or VAD.

Note: `ff_siwis`, Kokoro's only French voice, has a France accent. We accept that; the content is Québec-first.

## Run

```sh
cd services/tts
uv sync
uv run python -m frenchia_tts        # or: uv run frenchia-tts
```

Python 3.12 only (misaki needs <3.13). Startup loads the model on a dedicated worker thread and
warms it up (a few seconds on first run: voice download plus Metal warm-up). `/health` returns 503
`{"status":"loading"}` until ready. Once the model and voice are cached, set `HF_HUB_OFFLINE=1`
to run with no network access.

## API

```sh
curl -s localhost:8791/health
curl -s localhost:8791/v1/audio/voices
curl -s localhost:8791/v1/audio/speech -H 'content-type: application/json' \
  -d '{"input":"Bonjour, comment ça va aujourd’hui ?","speed":1.0}' -o out.wav -D -
```

`POST /v1/audio/speech` body: `{"model"?, "input", "voice"? = default, "speed"? = 1.0 (0.5-1.5), "response_format"? = "wav"}`.
Returns `audio/wav` (PCM16, mono, 24 kHz) with headers `X-Audio-Duration-Seconds`,
`X-Synthesis-Seconds`, `X-Chunks`. Text is split into sentences (French typography and
abbreviation aware), synthesized per chunk and joined with short silences.

Errors are `{"error":{"code","message"}}`:

| HTTP | code | when |
|---|---|---|
| 422 | `validation_error` / `unknown_voice` | empty input, speed out of range, unsupported format, unknown voice |
| 413 | `input_too_long` | input over `TTS_MAX_CHARS` |
| 503 | `loading` / `error` | model not ready |
| 500 | `synthesis_failed` | synthesis raised (traceback is logged) |

## Configuration (env vars)

| var | default |
|---|---|
| `TTS_HOST` / `TTS_PORT` | `127.0.0.1` / `8791` |
| `TTS_MODEL` | `mlx-community/Kokoro-82M-bf16` |
| `TTS_DEFAULT_VOICE` / `TTS_LANG_CODE` | `ff_siwis` / `f` |
| `TTS_MAX_CHARS` | `2000` |
| `TTS_MLX_CACHE_LIMIT_MB` | `256` (`none` disables) |
| `TTS_SENTENCE_PAUSE_MS` | `120` |
| `TTS_LOG_LEVEL` | `INFO` |
| `TTS_ALLOW_NON_LOOPBACK` | unset; binding a non-loopback host is refused unless `1` |

## Design notes

MLX streams are per-thread, so the model is loaded and every synthesis runs on one
`ThreadPoolExecutor(max_workers=1)`; handlers `await` it. This serializes synthesis and avoids
"no Stream(gpu,0) in current thread" errors.

## Tests and lint

```sh
uv run pytest            # fast unit and API tests (fake synthesizer)
uv run pytest -m live    # loads the real model
uv run ruff check . && uv run ruff format --check . && uv run mypy
uv run python scripts/measure_memory.py
```

## Memory findings

See `MEMORY.md`. Peak Metal about 2.5 GB, active about 0.3 GB after synthesis, RSS about 0.4 GB;
RTF about 0.05 to 0.1 (a 650-char paragraph in about 2 s). The cache limit does not hurt latency, so the default is 256 MB.
