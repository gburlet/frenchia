"""DRF exception handler: maps inference failures to typed JSON errors the UI can degrade on."""

from typing import Any

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from inference.errors import (
    InferenceError,
    InferenceTimeout,
    InferenceUnavailable,
    InvalidOutput,
    InvalidRequest,
)

_STATUS = [
    (InferenceUnavailable, 503, "unavailable"),
    (InferenceTimeout, 504, "timeout"),
    (InvalidRequest, 400, "invalid_request"),
    (InvalidOutput, 502, "invalid_output"),
    (InferenceError, 502, "error"),
]


def exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    if isinstance(exc, InferenceError):
        for cls, status, suffix in _STATUS:
            if isinstance(exc, cls):
                return Response(
                    {"detail": str(exc), "code": f"{exc.service}_{suffix}"}, status=status
                )
    return drf_exception_handler(exc, context)
