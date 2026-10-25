"""Process-wide cache of file-backed reference content, reloaded when the files change.

The conjugation reference (~1 MB of JSON) and the verb/vocabulary banks are read on every drill
request; parsing them each time would dominate the response time."""

import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from django.conf import settings

from contentkit.banks import Banks, load_banks
from contentkit.reference import Reference

_lock = threading.Lock()
_cache: dict[str, tuple[tuple[tuple[str, float], ...], Any]] = {}


def _root() -> Path:
    return Path(settings.CONTENT_DIR)


def _signature(paths: list[Path]) -> tuple[tuple[str, float], ...]:
    return tuple((str(p), p.stat().st_mtime) for p in paths if p.exists())


def _cached[T](key: str, paths: list[Path], load: Callable[[], T]) -> T:
    signature = _signature(paths)
    with _lock:
        hit = _cache.get(key)
        if hit is not None and hit[0] == signature:
            value: T = hit[1]
            return value
        value = load()
        _cache[key] = (signature, value)
        return value


def reference() -> Reference:
    root = _root()
    files = [root / "reference" / n for n in ("nouns.json", "conjugations.json", "quebec.yaml")]
    return _cached("reference", files, lambda: Reference.load(root))


def banks() -> Banks:
    root = _root()
    files = [
        root / "verbs" / "sets.yaml",
        root / "vocabulary" / "themes.yaml",
        *sorted((root / "verbs" / "bank").glob("*.yaml")),
        *sorted((root / "vocabulary" / "sets").glob("*.yaml")),
    ]
    return _cached("banks", files, lambda: load_banks(root))


def clear() -> None:
    with _lock:
        _cache.clear()
