"""Content-addressed WAV cache: identical text, voice, speed and model are synthesized once.
Files live under AUDIO_CACHE_DIR/<2-char prefix>/<sha256>.wav and are written atomically."""

import hashlib
import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .tts import SpeechSynth

KEY_RE = re.compile(r"^[0-9a-f]{64}$")


def normalize_text(text: str) -> str:
    return " ".join(unicodedata.normalize("NFC", text).split())


@dataclass(frozen=True)
class AudioClip:
    key: str
    path: Path
    cached: bool


class AudioCache:
    def __init__(self, root: Path, synth: SpeechSynth) -> None:
        self.root = root
        self.synth = synth

    def key(self, text: str, speed: float) -> str:
        material = f"{self.synth.model}|{self.synth.voice}|{speed:.2f}|{normalize_text(text)}"
        return hashlib.sha256(material.encode()).hexdigest()

    def path(self, key: str) -> Path | None:
        """Path of a cached clip, or None if the key is malformed or not cached."""
        if not KEY_RE.match(key):
            return None
        path = self.root / key[:2] / f"{key}.wav"
        return path if path.is_file() else None

    def get_or_create(self, text: str, *, speed: float = 1.0) -> AudioClip:
        text = normalize_text(text)
        key = self.key(text, speed)
        if existing := self.path(key):
            return AudioClip(key, existing, cached=True)
        audio = self.synth.synthesize(text, speed=speed)
        target = self.root / key[:2] / f"{key}.wav"
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(audio)
            os.replace(tmp, target)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
        return AudioClip(key, target, cached=False)
