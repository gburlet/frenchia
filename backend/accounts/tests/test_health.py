from unittest.mock import patch

import pytest
from django.db import OperationalError
from django.test import Client


@pytest.mark.django_db
def test_health_ok(client: Client) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["services"] == {"database": "ok", "llm": "ok", "tts": "ok"}
    assert body["version"]


def test_health_degraded(client: Client) -> None:
    with patch("config.health.connection.cursor", side_effect=OperationalError("down")):
        response = client.get("/api/health")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"]["database"] == "error"


@pytest.mark.django_db
def test_health_inference_down_is_degraded_not_failing(client: Client) -> None:
    with patch("inference.fakes.FakeChatModel.health", return_value=False):
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["services"] == {"database": "ok", "llm": "error", "tts": "ok"}
