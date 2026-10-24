from django.test import Client


def test_schema(client: Client) -> None:
    response = client.get("/api/schema/", HTTP_ACCEPT="application/vnd.oai.openapi+json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    for path in (
        "/api/health",
        "/api/auth/csrf",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/me",
    ):
        assert path in paths
