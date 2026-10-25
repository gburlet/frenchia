from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import User
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision
from exercises.models import ExerciseAttempt
from exercises.services import submit_attempt
from progress.stats import streak

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 25)


def days(*offsets: int) -> set[date]:
    return {TODAY - timedelta(days=o) for o in offsets}


@pytest.mark.parametrize(
    ("active", "current", "longest", "today"),
    [
        (set(), 0, 0, False),
        (days(0, 1, 2), 3, 3, True),
        (days(1, 2), 2, 2, False),  # today not studied yet: the streak is still alive
        (days(2, 3), 0, 2, False),  # a missed day breaks it
        (days(0, 5, 6, 7, 8), 1, 4, True),
    ],
)
def test_streak(active: set[date], current: int, longest: int, today: bool) -> None:
    assert streak(active, TODAY) == {"current": current, "longest": longest, "studied_today": today}


@pytest.fixture
def client_user(client: Client, settings: Any, tmp_path: Path) -> tuple[Client, User]:
    root = make_repo(tmp_path / "content")
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    user = User.objects.create_user("marie", password="pw-123456789")
    client.force_login(user)
    return client, user


def test_dashboard_summarises_activity(client_user: tuple[Client, User]) -> None:
    client, user = client_user
    fill = ExerciseRevision.objects.get(exercise__stable_id="a2-passe-compose-er/ex-01")
    submit_attempt(user, fill, "ai mangé", 30_000)
    submit_attempt(user, fill, "ai mange", 60 * 60_000)  # an hour-long tab counts as 3 minutes
    submit_attempt(user, fill, "suis mangé", 30_000)
    old = submit_attempt(user, fill, "ai mangé", 30_000)
    ExerciseAttempt.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=1))
    body = client.get("/api/dashboard").json()
    assert body["streak"] == {"current": 2, "longest": 2, "studied_today": True}
    assert body["minutes"] == {"today": 4, "week": 4}
    assert body["accuracy_week"]["graded"] == 4
    assert body["history"][-1]["items"] == 3 and body["history"][-2]["items"] == 1
    assert body["history"][-1]["by_kind"] == {"exercises": 3}
    assert body["lessons"] == {"published": 1, "completed": 0}
    assert body["topics"][0]["id"] == "passe-compose-avoir"
    assert body["weak_topics"] == [] or body["weak_topics"][0]["id"] == "passe-compose-avoir"
    assert body["vocab"]["due_now"] == 0 and body["review"] is None


def test_dashboard_for_a_new_learner(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    body = client.get("/api/dashboard").json()
    assert body["streak"]["current"] == 0 and body["accuracy_week"]["accuracy"] is None
    assert len(body["history"]) == 14 and body["topics"] == [] and body["mistakes"] == []
