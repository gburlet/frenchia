from pathlib import Path
from typing import Any

import pytest
from django.core.management import CommandError, call_command

from accounts.models import User
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision
from exercises.models import ExerciseAttempt, MistakeOccurrence
from exercises.services import submit_attempt
from progress.models import LessonProgress, TopicMastery

pytestmark = pytest.mark.django_db


@pytest.fixture
def learners(settings: Any, tmp_path: Path) -> tuple[User, User]:
    root = make_repo(tmp_path / "content")
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    fill = ExerciseRevision.objects.get(exercise__stable_id="a2-passe-compose-er/ex-01")
    marie, paul = (
        User.objects.create_user(name, password="pw-1234567") for name in ("marie", "paul")
    )
    for user in (marie, paul):
        attempt = submit_attempt(user, fill, "suis mangé", 30_000)
        MistakeOccurrence.objects.create(attempt=attempt, category="auxiliary", span="suis")
    return marie, paul


def test_clears_only_the_named_user(learners: tuple[User, User]) -> None:
    marie, paul = learners
    assert MistakeOccurrence.objects.filter(attempt__user=marie).exists()
    call_command("clear_progress", "marie", interactive=False)
    for model in (ExerciseAttempt, LessonProgress, TopicMastery):
        assert not model.objects.filter(user=marie).exists()
        assert model.objects.filter(user=paul).exists()
    assert not MistakeOccurrence.objects.filter(attempt__user=marie).exists()
    assert User.objects.filter(username="marie").exists()


def test_dry_run_and_cancel_keep_everything(
    learners: tuple[User, User], monkeypatch: pytest.MonkeyPatch
) -> None:
    marie, _ = learners
    call_command("clear_progress", "marie", dry_run=True)
    monkeypatch.setattr("builtins.input", lambda _prompt: "no")
    with pytest.raises(CommandError, match="Cancelled"):
        call_command("clear_progress", "marie")
    assert ExerciseAttempt.objects.filter(user=marie).exists()


def test_unknown_user() -> None:
    with pytest.raises(CommandError, match="No user named"):
        call_command("clear_progress", "nobody", interactive=False)
