from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from inference.providers import reset_providers


@pytest.fixture(autouse=True)
def fake_inference(settings: Any, tmp_path: Path) -> Iterator[None]:
    """Tests never call the native LLM/TTS: use the deterministic fakes and a temp cache."""
    settings.INFERENCE = {**settings.INFERENCE, "MODE": "fake"}
    settings.AUDIO_CACHE_DIR = tmp_path / "audio"
    reset_providers()
    yield
    reset_providers()
