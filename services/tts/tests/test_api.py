import asyncio
import io
import wave
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from frenchia_tts.app import create_app
from frenchia_tts.config import Settings
from frenchia_tts.engine import Synthesis, to_wav


class FakeSynth:
    model_name = "fake"
    sample_rate = 24000
    voices = ["ff_siwis"]

    def __init__(self) -> None:
        self.status = "ok"
        self.error: str | None = None
        self.in_flight = 0
        self.max_in_flight = 0
        self.fail = False
        self._lock = asyncio.Lock()  # stands in for the engine's single worker thread

    async def start(self) -> None:
        return None

    async def synthesize(self, text: str, voice: str, speed: float) -> Synthesis:
        async with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
            await asyncio.sleep(0.02)
            self.in_flight -= 1
        if self.fail:
            raise RuntimeError("boom")
        import numpy as np

        audio = np.full(int(24000 * len(text) / 100 / speed), 0.1, dtype=np.float32)
        return Synthesis(to_wav(audio), len(audio) / 24000, 0.01, 2)

    def metal_mb(self) -> tuple[float, float]:
        return 10.0, 20.0

    def close(self) -> None:
        return None


@pytest.fixture
def fake() -> FakeSynth:
    return FakeSynth()


@pytest.fixture
def client(fake: FakeSynth) -> Iterator[TestClient]:
    with TestClient(create_app(Settings(max_chars=100), fake)) as c:
        yield c


def post(c: TestClient, **body: object) -> object:
    return c.post("/v1/audio/speech", json={"input": "Bonjour", **body})


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    j = r.json()
    assert r.status_code == 200 and j["status"] == "ok" and j["sample_rate"] == 24000
    assert j["voices"] == ["ff_siwis"] and j["metal_peak_mb"] == 20.0 and "uptime_s" in j


@pytest.mark.parametrize("status", ["loading", "error"])
def test_health_not_ready(client: TestClient, fake: FakeSynth, status: str) -> None:
    fake.status = status
    r = client.get("/health")
    assert r.status_code == 503 and r.json()["status"] == status


def test_voices(client: TestClient) -> None:
    assert client.get("/v1/audio/voices").json() == {
        "voices": [{"id": "ff_siwis", "language": "fr-fr", "gender": "female"}]
    }


def test_speech_wav(client: TestClient) -> None:
    r = client.post(
        "/v1/audio/speech", json={"input": "Bonjour", "model": "x", "voice": "ff_siwis"}
    )
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    assert r.content[:4] == b"RIFF" and r.content[8:12] == b"WAVE"
    with wave.open(io.BytesIO(r.content)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (24000, 1, 2)
    assert float(r.headers["X-Audio-Duration-Seconds"]) > 0
    assert r.headers["X-Chunks"] == "2" and "X-Synthesis-Seconds" in r.headers


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"input": ""}, 422),
        ({"input": "   "}, 422),
        ({"input": "a", "speed": 0.1}, 422),
        ({"input": "a", "speed": 2.0}, 422),
        ({"input": "a", "voice": "nope"}, 422),
        ({"input": "a", "response_format": "mp3"}, 422),
        ({}, 422),
        ({"input": "x" * 101}, 413),
    ],
)
def test_errors(client: TestClient, body: dict[str, object], status: int) -> None:
    r = client.post("/v1/audio/speech", json=body)
    assert r.status_code == status
    err = r.json()["error"]
    assert err["code"] and err["message"]


def test_loading_503(client: TestClient, fake: FakeSynth) -> None:
    fake.status = "loading"
    r = post(client)
    assert r.status_code == 503 and r.json()["error"]["code"] == "loading"  # type: ignore[attr-defined]


def test_synthesis_failure_500(client: TestClient, fake: FakeSynth) -> None:
    fake.fail = True
    r = post(client)
    assert r.status_code == 500 and r.json()["error"]["code"] == "synthesis_failed"  # type: ignore[attr-defined]


def test_concurrent_requests_serialized(client: TestClient, fake: FakeSynth) -> None:
    with ThreadPoolExecutor(8) as ex:
        codes = list(ex.map(lambda _: post(client).status_code, range(8)))  # type: ignore[attr-defined]
    assert codes == [200] * 8 and fake.max_in_flight == 1


def test_settings_refuse_non_loopback() -> None:
    with pytest.raises(SystemExit):
        Settings.from_env({"TTS_HOST": "0.0.0.0"})
    assert (
        Settings.from_env({"TTS_HOST": "0.0.0.0", "TTS_ALLOW_NON_LOOPBACK": "1"}).host == "0.0.0.0"
    )
    assert Settings.from_env({"TTS_MLX_CACHE_LIMIT_MB": "none"}).mlx_cache_limit_mb is None
