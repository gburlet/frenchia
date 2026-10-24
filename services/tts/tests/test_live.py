"""Real-model tests: `pytest -m live`."""

import io
import wave
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest
from fastapi.testclient import TestClient

from frenchia_tts.app import create_app
from frenchia_tts.config import Settings

pytestmark = pytest.mark.live
TEXT = "Bonjour, comment ça va aujourd'hui ?"


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    import time

    with TestClient(create_app(Settings())) as c:
        for _ in range(300):
            if c.get("/health").status_code == 200:
                break
            time.sleep(0.5)
        else:
            pytest.fail("model did not load")
        yield c


def speak(c: TestClient, speed: float = 1.0, text: str = TEXT) -> bytes:
    r = c.post("/v1/audio/speech", json={"input": text, "speed": speed})
    assert r.status_code == 200, r.text
    return r.content


def duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data)) as w:
        return float(w.getnframes() / w.getframerate())


def test_real_synthesis(client: TestClient) -> None:
    data = speak(client)
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    with wave.open(io.BytesIO(data)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
        assert 1 < w.getnframes() / 24000 < 5
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
    assert float(np.sqrt(np.mean(pcm**2))) > 0.01


def test_slower_speed_is_longer(client: TestClient) -> None:
    assert duration(speak(client, 0.75)) > duration(speak(client, 1.0))


def test_multi_sentence_and_concurrency(client: TestClient) -> None:
    text = "Salut ! Je m'appelle Marie. M. Roy habite à Québec, et il coûte 3,5 euros."
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(lambda _: speak(client, text=text), range(4)))
    assert all(r[:4] == b"RIFF" for r in results)
    assert client.get("/health").json()["status"] == "ok"
