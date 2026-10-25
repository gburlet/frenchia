import logging
import threading
import time

from django.http import FileResponse, Http404
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from .errors import InferenceError
from .providers import get_audio_cache, get_chat_model
from .serializers import AudioClipSerializer, InferenceErrorSerializer, SpeechRequestSerializer

logger = logging.getLogger(__name__)


class AudioView(APIView):
    """Synthesize (or fetch from cache) French speech; returns a URL for the WAV."""

    @extend_schema(
        operation_id="audio_create",
        request=SpeechRequestSerializer,
        responses={200: AudioClipSerializer, 503: InferenceErrorSerializer},
    )
    def post(self, request: Request) -> Response:
        serializer = SpeechRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        clip = get_audio_cache().get_or_create(
            serializer.validated_data["text"], speed=serializer.validated_data["speed"]
        )
        return Response(
            {"key": clip.key, "url": f"/api/audio/{clip.key}.wav", "cached": clip.cached}
        )


class AudioFileView(APIView):
    @extend_schema(
        operation_id="audio_file",
        responses={
            (200, "audio/wav"): OpenApiTypes.BINARY,
            404: OpenApiResponse(description="Not cached"),
        },
    )
    def get(self, request: Request, key: str) -> FileResponse:
        path = get_audio_cache().path(key)
        if path is None:
            raise Http404
        response = FileResponse(path.open("rb"), content_type="audio/wav")
        # Content-addressed: a key's bytes never change.
        response["Cache-Control"] = "private, max-age=31536000, immutable"
        return response


_WARM_INTERVAL_S = 300
_last_warm = 0.0
_warm_lock = threading.Lock()


def _warm_in_background() -> None:
    try:
        get_chat_model().warm()
    except InferenceError:
        logger.info("LLM warm-up skipped: service unavailable")


class WarmView(APIView):
    """Fire-and-forget: load the LLM before the learner's first question (cold load ~30-40 s)."""

    @extend_schema(operation_id="llm_warm", request=None, responses={202: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        global _last_warm
        with _warm_lock:
            due = time.monotonic() - _last_warm > _WARM_INTERVAL_S
            if due:
                _last_warm = time.monotonic()
        if due:
            threading.Thread(target=_warm_in_background, daemon=True).start()
        return Response({"warming": due}, status=202)
