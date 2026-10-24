"""``python -m frenchia_tts`` / ``frenchia-tts``: run uvicorn, one worker, no reload."""

from __future__ import annotations

import logging

import uvicorn

from .app import create_app
from .config import Settings


def main() -> None:
    s = Settings.from_env()
    logging.basicConfig(level=s.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        create_app(s), host=s.host, port=s.port, workers=1, reload=False,
        log_level=s.log_level.lower(),
    )  # fmt: skip


if __name__ == "__main__":
    main()
