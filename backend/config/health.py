"""Health endpoint. Each service check is a function returning "ok" or "error".

Critical services (the database) make the endpoint return 503. The native inference
services are optional: if they are down the app still works, so the status is "degraded"
with HTTP 200, and the UI disables the features that need them."""

import logging
from collections.abc import Callable

from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from inference.health import check_llm, check_tts

logger = logging.getLogger(__name__)

VERSION = "0.1.0"


def check_database() -> str:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception:
        logger.exception("Database health check failed")
        return "error"
    return "ok"


# name -> (check, critical)
SERVICE_CHECKS: dict[str, tuple[Callable[[], str], bool]] = {
    "database": (check_database, True),
    "llm": (check_llm, False),
    "tts": (check_tts, False),
}

_health_serializer = inline_serializer(
    "Health",
    {
        "status": serializers.ChoiceField(choices=["ok", "degraded"]),
        "services": serializers.DictField(child=serializers.ChoiceField(choices=["ok", "error"])),
        "version": serializers.CharField(),
    },
)


class HealthView(APIView):
    authentication_classes: list[type] = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="health",
        responses={
            200: _health_serializer,
            503: OpenApiResponse(_health_serializer, description="A critical service is down."),
        },
    )
    def get(self, request: Request) -> Response:
        services = {name: check() for name, (check, _) in SERVICE_CHECKS.items()}
        critical_ok = all(
            services[name] == "ok" for name, (_, critical) in SERVICE_CHECKS.items() if critical
        )
        all_ok = all(value == "ok" for value in services.values())
        return Response(
            {"status": "ok" if all_ok else "degraded", "services": services, "version": VERSION},
            status=status.HTTP_200_OK if critical_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
