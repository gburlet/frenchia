import pytest
from django.test import Client

from accounts.models import User

PASSWORD = "s3cret-pass-123"


@pytest.fixture
def user(db: None) -> User:
    return User.objects.create_user("marie", "marie@example.com", PASSWORD)


@pytest.fixture
def csrf_client() -> Client:
    return Client(enforce_csrf_checks=True)


def _csrf(client: Client) -> str:
    response = client.get("/api/auth/csrf")
    assert response.status_code == 204
    return client.cookies["csrftoken"].value


def test_full_flow(csrf_client: Client, user: User) -> None:
    token = _csrf(csrf_client)

    response = csrf_client.post(
        "/api/auth/login",
        {"username": "marie", "password": PASSWORD},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 200
    assert response.json() == {
        "id": user.pk,
        "username": "marie",
        "email": "marie@example.com",
        "is_staff": False,
    }

    me = csrf_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "marie"

    # Login rotates the CSRF token; re-read it from the cookie.
    token = csrf_client.cookies["csrftoken"].value
    assert csrf_client.post("/api/auth/logout", headers={"X-CSRFToken": token}).status_code == 204
    assert csrf_client.get("/api/auth/me").status_code == 403


def test_login_requires_csrf(csrf_client: Client, user: User) -> None:
    response = csrf_client.post(
        "/api/auth/login",
        {"username": "marie", "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403


def test_bad_login(csrf_client: Client, user: User) -> None:
    token = _csrf(csrf_client)
    response = csrf_client.post(
        "/api/auth/login",
        {"username": "marie", "password": "wrong"},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid username or password."}


def test_me_anonymous(client: Client) -> None:
    assert client.get("/api/auth/me").status_code == 403
