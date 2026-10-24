"""Health endpoint. Each service check is a function returning "ok" or "error"."""

import logging
from collections.abc import Callable

from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

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


# Phase 2: register "llm" and "tts" checks here.
SERVICE_CHECKS: dict[str, Callable[[], str]] = {
    "database": check_database,
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
            503: OpenApiResponse(_health_serializer, description="A service is unavailable."),
        },
    )
    def get(self, request: Request) -> Response:
        services = {name: check() for name, check in SERVICE_CHECKS.items()}
        healthy = all(value == "ok" for value in services.values())
        return Response(
            {"status": "ok" if healthy else "degraded", "services": services, "version": VERSION},
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )
