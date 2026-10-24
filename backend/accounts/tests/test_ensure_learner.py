import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User


@pytest.fixture
def admin_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    monkeypatch.setenv("FRENCHIA_ADMIN_USERNAME", "learner")
    monkeypatch.setenv("FRENCHIA_ADMIN_PASSWORD", "first-pass-123")
    monkeypatch.setenv("FRENCHIA_ADMIN_EMAIL", "learner@example.com")
    return monkeypatch


@pytest.mark.django_db
def test_idempotent_and_updates_password(admin_env: pytest.MonkeyPatch) -> None:
    call_command("ensure_learner")
    call_command("ensure_learner")
    user = User.objects.get(username="learner")
    assert User.objects.count() == 1
    assert user.is_superuser and user.is_staff
    assert user.check_password("first-pass-123")

    admin_env.setenv("FRENCHIA_ADMIN_PASSWORD", "second-pass-456")
    call_command("ensure_learner")
    user.refresh_from_db()
    assert user.check_password("second-pass-456")


@pytest.mark.django_db
def test_missing_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("USERNAME", "PASSWORD", "EMAIL"):
        monkeypatch.delenv(f"FRENCHIA_ADMIN_{name}", raising=False)
    with pytest.raises(CommandError, match="FRENCHIA_ADMIN_USERNAME"):
        call_command("ensure_learner")
