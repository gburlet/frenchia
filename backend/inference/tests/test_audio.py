from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import User
from inference.errors import InferenceUnavailable
from inference.providers import get_audio_cache, get_speech_synth


@pytest.fixture
def auth_client(client: Client, db: None) -> Client:
    user = User.objects.create_user("marie", password="pw-123456789")
    client.force_login(user)
    return client


def test_cache_normalizes_text_and_synthesizes_once() -> None:
    cache = get_audio_cache()
    first = cache.get_or_create("Bonjour   tout le monde", speed=1.0)
    second = cache.get_or_create(" Bonjour tout le monde ", speed=1.0)
    assert first.key == second.key
    assert (first.cached, second.cached) == (False, True)
    assert second.path.read_bytes().startswith(b"RIFF")
    assert get_speech_synth().calls == [("Bonjour tout le monde", 1.0)]  # type: ignore[attr-defined]


def test_cache_key_depends_on_speed() -> None:
    cache = get_audio_cache()
    assert cache.key("Salut", 1.0) != cache.key("Salut", 0.75)


@pytest.mark.parametrize("key", ["../../etc/passwd", "abc", "Z" * 64])
def test_cache_rejects_malformed_keys(key: str) -> None:
    assert get_audio_cache().path(key) is None


def test_audio_api_requires_login(client: Client, db: None) -> None:
    assert (
        client.post("/api/audio", {"text": "Salut"}, content_type="application/json").status_code
        == 403
    )


def test_audio_api_returns_url_then_serves_wav(auth_client: Client) -> None:
    response = auth_client.post(
        "/api/audio",
        {"text": "On soupe à six heures.", "speed": 0.9},
        content_type="application/json",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["cached"] is False
    assert body["url"] == f"/api/audio/{body['key']}.wav"

    audio = auth_client.get(body["url"])
    assert audio.status_code == 200
    assert audio["Content-Type"] == "audio/wav"
    assert "immutable" in audio["Cache-Control"]
    assert b"".join(audio.streaming_content).startswith(b"RIFF")  # type: ignore[attr-defined]


def test_audio_api_validates_input(auth_client: Client) -> None:
    response = auth_client.post(
        "/api/audio", {"text": "Salut", "speed": 3}, content_type="application/json"
    )
    assert response.status_code == 400
    assert "speed" in response.json()


def test_unknown_audio_is_404(auth_client: Client) -> None:
    assert auth_client.get(f"/api/audio/{'a' * 64}.wav").status_code == 404


def test_tts_down_returns_typed_503(auth_client: Client) -> None:
    with patch(
        "inference.fakes.FakeSpeechSynth.synthesize",
        side_effect=InferenceUnavailable("tts", "The speech service is not running"),
    ):
        response = auth_client.post(
            "/api/audio", {"text": "Salut"}, content_type="application/json"
        )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "The speech service is not running",
        "code": "tts_unavailable",
    }


def test_warm_is_throttled(auth_client: Client) -> None:
    import inference.views as views

    views._last_warm = 0.0
    with patch("inference.views.threading.Thread") as thread:
        assert auth_client.post("/api/llm/warm").json() == {"warming": True}
        assert auth_client.post("/api/llm/warm").json() == {"warming": False}
    assert thread.call_count == 1


def test_bold_markers_are_not_spoken() -> None:
    from inference.audio import normalize_text

    assert normalize_text("Je **mange**  une pomme.") == "Je mange une pomme."
