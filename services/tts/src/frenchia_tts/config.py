"""Environment-driven settings. Set ``HF_HUB_OFFLINE=1`` to skip the network once cached."""

from __future__ import annotations

import os
from dataclasses import dataclass

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 8791
    model: str = "mlx-community/Kokoro-82M-bf16"
    default_voice: str = "ff_siwis"
    lang_code: str = "f"
    max_chars: int = 2000
    mlx_cache_limit_mb: int | None = 256
    sentence_pause_ms: int = 120
    log_level: str = "INFO"
    allow_non_loopback: bool = False

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> Settings:
        e = os.environ if env is None else env
        d = cls()

        def get(name: str, default: str) -> str:
            return e.get(f"TTS_{name}", default)

        limit = get("MLX_CACHE_LIMIT_MB", str(d.mlx_cache_limit_mb))
        s = cls(
            host=get("HOST", d.host),
            port=int(get("PORT", str(d.port))),
            model=get("MODEL", d.model),
            default_voice=get("DEFAULT_VOICE", d.default_voice),
            lang_code=get("LANG_CODE", d.lang_code),
            max_chars=int(get("MAX_CHARS", str(d.max_chars))),
            # "none" or "0" disables the explicit cache limit (MLX default).
            mlx_cache_limit_mb=None if limit.lower() in {"none", "0", ""} else int(limit),
            sentence_pause_ms=int(get("SENTENCE_PAUSE_MS", str(d.sentence_pause_ms))),
            log_level=get("LOG_LEVEL", d.log_level).upper(),
            allow_non_loopback=get("ALLOW_NON_LOOPBACK", "0") == "1",
        )
        if s.host not in LOOPBACK_HOSTS and not s.allow_non_loopback:
            raise SystemExit(
                f"Refusing to bind to non-loopback host {s.host!r}; set TTS_ALLOW_NON_LOOPBACK=1."
            )
        return s
