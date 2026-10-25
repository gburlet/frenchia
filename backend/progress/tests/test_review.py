from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import User
from authoring.tests.scripted import ScriptedChat
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision
from exercises.services import submit_attempt
from progress import review
from progress.models import LessonProgress, ReviewItem, ReviewSet

pytestmark = pytest.mark.django_db


@pytest.fixture
def user(settings: Any, tmp_path: Path) -> User:
    root = make_repo(tmp_path / "content")
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    return User.objects.create_user("marie", password="pw-123456789")


def revision(exercise_id: str) -> ExerciseRevision:
    return ExerciseRevision.objects.get(exercise__stable_id=f"a2-passe-compose-er/{exercise_id}")


def miss_fill_blank(user: User, times: int = 2) -> None:
    for _ in range(times):
        submit_attempt(user, revision("ex-01"), "ai mangée pas", 4000)


def test_weak_topics_come_from_mastery(user: User) -> None:
    assert review.weak_topics(user) == []
    miss_fill_blank(user)
    [weak] = review.weak_topics(user)
    assert weak.topic.slug == "passe-compose-avoir" and weak.ewma == 0.0
    assert weak.reason == "0% recent accuracy over 2 tries"


def test_set_puts_missed_items_first_and_skips_comprehension(
    user: User, django_capture_on_commit_callbacks: Any
) -> None:
    miss_fill_blank(user)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        created = review.build_set(user)
    assert [(i.exercise_revision.payload["id"], i.source) for i in created.items.all()] == [
        ("ex-01", ReviewItem.Source.MISSED),
        ("ex-02", ReviewItem.Source.UNSEEN),
    ]
    assert created.extras == ReviewSet.Extras.QUEUED and len(callbacks) == 1  # for the worker


def test_new_learner_reviews_opened_lessons_or_gets_a_clear_error(user: User) -> None:
    with pytest.raises(review.ReviewUnavailable):
        review.build_set(user, generate=False)
    LessonProgress.objects.create(user=user, lesson=revision("ex-01").lesson_revision.lesson)
    created = review.build_set(user, generate=False)
    assert created.topics[0]["reason"] == "not practised much yet"
    assert created.items.count() == 2


def test_starting_a_new_set_closes_the_unfinished_one(user: User) -> None:
    miss_fill_blank(user)
    first = review.build_set(user, generate=False)
    second = review.build_set(user, generate=False)
    first.refresh_from_db()
    assert first.completed_at is not None and review.current_set(user) == second


class FlaggingChat(ScriptedChat):
    """The critic rejects one generated translation."""

    def complete(self, messages: Any, **kwargs: Any) -> Any:
        if (kwargs.get("json_schema") or {}).get("title") == "Critique" and "mangé 1" in str(
            messages[-1].content
        ):
            return super().complete(
                [*messages[:-1], type(messages[-1])("user", "Sentence: a parlé son ami\n")],
                **kwargs,
            )
        return super().complete(messages, **kwargs)


def test_generated_extras_are_validated_labelled_and_kept_out_of_lessons(
    user: User, client: Client
) -> None:
    miss_fill_blank(user)
    created = review.build_set(user, generate=False)
    created.extras = ReviewSet.Extras.QUEUED
    created.save()
    with patch("progress.review.get_chat_model", return_value=FlaggingChat()):
        review.generate_extras(created.pk)
    created.refresh_from_db()
    assert created.extras == ReviewSet.Extras.READY, created.extras_error
    generated = list(created.items.filter(source=ReviewItem.Source.GENERATED))
    payloads = [i.exercise_revision.payload for i in generated]
    assert [p["type"] for p in payloads] == ["fill_blank", "fill_blank", "translate"]
    assert all(p["grammar_topics"] == ["passe-compose-avoir"] for p in payloads)
    assert all(
        i.exercise_revision.origin == ExerciseRevision.Origin.PERSONALIZED for i in generated
    )
    assert any("AI critic" in d for d in created.extras_log[0]["dropped"])  # "mangé 1" dropped
    # The mistake made it into the prompt.
    client.force_login(user)
    lesson = client.get("/api/lessons/a2-passe-compose-er").json()
    assert len(lesson["exercises"]) == 3
    detail = client.get(f"/api/review/{created.pk}").json()
    assert [i["ai_generated"] for i in detail["items"]] == [False, False, True, True, True]
    assert "answers" not in str(detail["items"][-1]["exercise"])
    for _ in range(10):  # the Translation Station never serves personalized exercises
        served = client.get("/api/practice/translate/next").json()
        assert served["exercise_revision_id"] == revision("ex-02").pk


def test_review_api_tracks_answers_and_completion(
    user: User, client: Client, django_capture_on_commit_callbacks: Any
) -> None:
    client.force_login(user)
    assert client.post("/api/review").status_code == 404
    miss_fill_blank(user)
    with django_capture_on_commit_callbacks(execute=False):
        created = client.post("/api/review").json()
    assert client.get("/api/review").json()["current"]["id"] == created["id"]
    first = created["items"][0]["exercise"]
    assert created["items"][0]["source_label"] == "answered wrong last time"
    client.post(
        f"/api/exercise-revisions/{first['exercise_revision_id']}/attempts",
        {"answer": "ai mangé"},
        content_type="application/json",
    )
    detail = client.get(f"/api/review/{created['id']}").json()
    assert [i["result"] for i in detail["items"]] == ["correct", None]
    done = client.post(f"/api/review/{created['id']}/complete").json()
    assert done["completed_at"] is not None
    assert client.get("/api/review").json()["current"] is None
