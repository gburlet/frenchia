import json

import httpx
import pytest

from inference.errors import InferenceUnavailable, InvalidRequest
from inference.fakes import silent_wav
from inference.tts import HttpSpeechSynth


def synth(handler: object) -> HttpSpeechSynth:
    return HttpSpeechSynth(
        "http://tts.test",
        model="kokoro",
        voice="ff_siwis",
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
    )


def test_synthesize_posts_openai_speech_request() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=silent_wav(0.1), headers={"content-type": "audio/wav"})

    audio = synth(handler).synthesize("Bonjour", speed=0.8)
    assert audio.startswith(b"RIFF")
    assert seen["path"] == "/v1/audio/speech"
    assert seen["body"] == {
        "model": "kokoro",
        "input": "Bonjour",
        "voice": "ff_siwis",
        "speed": 0.8,
        "response_format": "wav",
    }


def test_rejected_input_maps_to_invalid_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            413, json={"error": {"code": "input_too_long", "message": "Too long"}}
        )

    with pytest.raises(InvalidRequest, match="Too long"):
        synth(handler).synthesize("x" * 5000)


def test_loading_and_down_map_to_unavailable() -> None:
    def loading(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": {"code": "loading", "message": "Loading"}})

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    for handler in (loading, down):
        with pytest.raises(InferenceUnavailable):
            synth(handler).synthesize("Bonjour")
