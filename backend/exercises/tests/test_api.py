from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.test import Client

from accounts.models import User
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision, Lesson
from exercises.grading import JudgeError, JudgeOutput
from exercises.models import ExerciseAttempt, MistakeOccurrence
from inference.fakes import FakeChatModel
from progress.models import LessonProgress, TopicMastery

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_user(client: Client, settings: Any, tmp_path: Path) -> tuple[Client, User]:
    root = make_repo(tmp_path / "content")
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    user = User.objects.create_user("marie", password="pw-123456789")
    client.force_login(user)
    return client, user


def revision(exercise_id: str) -> ExerciseRevision:
    return ExerciseRevision.objects.get(exercise__stable_id=f"a2-passe-compose-er/{exercise_id}")


def test_curriculum_lists_levels_units_and_published_flags(
    client_user: tuple[Client, User],
) -> None:
    client, _ = client_user
    body = client.get("/api/curriculum").json()
    level = body["levels"][0]
    assert (level["level"], level["title"]) == ("A2", "Élémentaire")
    lessons = level["units"][0]["lessons"]
    assert [(lesson["id"], lesson["published"]) for lesson in lessons] == [
        ("a2-passe-compose-er", True),
        ("a2-imparfait", False),
    ]
    assert lessons[0]["progress"]["status"] == "not_started"


def test_lesson_detail_hides_answers(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    body = client.get("/api/lessons/a2-passe-compose-er").json()
    assert body["revision"]["content_version"] == 1 and len(body["sections"]) == 2
    text = str(body["exercises"])
    for secret in ("accepted_answers", "answers", "answer_index", "ai mangé", "On a magasiné"):
        assert secret not in text
    assert all("exercise_revision_id" in e for e in body["exercises"])
    assert client.get("/api/lessons/a2-imparfait").status_code == 404


def test_fill_blank_attempt_records_mastery(client_user: tuple[Client, User]) -> None:
    client, user = client_user
    response = client.post(
        f"/api/exercise-revisions/{revision('ex-01').pk}/attempts",
        {"answer": "ai mangé", "time_spent_ms": 4000},
        content_type="application/json",
    )
    assert response.status_code == 201
    body = response.json()
    assert (body["verdict"], body["grading"], body["correct_answer"]) == (
        "correct",
        "deterministic",
        "Hier, j'ai mangé une poutine.",
    )
    mastery = TopicMastery.objects.get(user=user, topic_id="passe-compose-avoir")
    assert (mastery.attempts, mastery.correct, mastery.ewma) == (1, 1, 1.0)
    assert LessonProgress.objects.get(user=user).status == "in_progress"


def test_translate_attempt_graded_by_llm_records_mistakes(client_user: tuple[Client, User]) -> None:
    client, user = client_user
    judge = JudgeOutput.model_validate(
        {
            "errors": [
                {
                    "category": "auxiliary",
                    "severity": "error",
                    "span": "sommes",
                    "explanation": "magasiner takes avoir.",
                }
            ],
            "corrected": "Nous avons magasiné.",
            "summary": "Almost.",
            "register_note": "",
        }
    )
    with patch(
        "exercises.services.get_chat_model",
        return_value=FakeChatModel(lambda m: judge.model_dump_json()),
    ):
        body = client.post(
            f"/api/exercise-revisions/{revision('ex-02').pk}/attempts",
            {"answer": "Nous sommes magasiné."},
            content_type="application/json",
        ).json()
    assert (body["verdict"], body["grading"]) == ("incorrect", "llm")
    assert body["accepted_answers"] == ["On a magasiné.", "Nous avons magasiné."]
    mistake = MistakeOccurrence.objects.get()
    assert (mistake.category, mistake.grammar_topic_id) == ("auxiliary", "passe-compose-avoir")


def test_pending_then_regrade(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    from inference.errors import InferenceUnavailable

    def down(m: object) -> str:
        raise InferenceUnavailable("llm", "down")

    with patch("exercises.services.get_chat_model", return_value=FakeChatModel(down)):
        body = client.post(
            f"/api/exercise-revisions/{revision('ex-02').pk}/attempts",
            {"answer": "Nous avons fait du shopping."},
            content_type="application/json",
        ).json()
    assert body["status"] == "pending" and body["verdict"] is None
    ok = JudgeOutput(
        errors=[], corrected="Nous avons fait du shopping.", summary="Good!", register_note=""
    )
    with patch(
        "exercises.services.get_chat_model",
        return_value=FakeChatModel(lambda m: ok.model_dump_json()),
    ):
        body = client.post(f"/api/attempts/{body['attempt_id']}/regrade").json()
    assert (body["status"], body["verdict"]) == ("graded", "correct")


def test_choice_attempt_validation_and_result(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    url = f"/api/exercise-revisions/{revision('ex-03').pk}/attempts"
    assert client.post(url, {"answer": 9}, content_type="application/json").status_code == 400
    assert client.post(url, {"answer": "zero"}, content_type="application/json").status_code == 400
    body = client.post(url, {"answer": 1}, content_type="application/json").json()
    assert (body["verdict"], body["correct_index"], body["explanation"]) == (
        "incorrect",
        0,
        "« j'ai magasiné »",
    )


def test_dispute_and_accept_answer_updates_the_content_file(
    client_user: tuple[Client, User], settings: Any
) -> None:
    client, _ = client_user
    from exercises.services import accept_disputed_answer

    with patch(
        "exercises.services.get_chat_model",
        return_value=FakeChatModel(
            lambda m: JudgeOutput(
                errors=[
                    JudgeError(
                        category="word_choice", severity="error", span="On a", explanation="x"
                    )
                ],
                corrected="Nous avons magasiné.",
                summary="x",
                register_note="",
            ).model_dump_json()
        ),
    ):
        body = client.post(
            f"/api/exercise-revisions/{revision('ex-02').pk}/attempts",
            {"answer": "On a fait les magasins."},
            content_type="application/json",
        ).json()
    assert client.post(
        f"/api/attempts/{body['attempt_id']}/dispute",
        {"comment": "fine in Québec"},
        content_type="application/json",
    ).json() == {"disputed": True}
    attempt = ExerciseAttempt.objects.get(pk=body["attempt_id"])
    path = accept_disputed_answer(attempt)
    assert "On a fait les magasins." in path.read_text()
    lesson = Lesson.objects.get(slug="a2-passe-compose-er")
    assert lesson.published_revision is not None and lesson.published_revision.content_version == 2
    attempt.refresh_from_db()
    assert (attempt.verdict, attempt.grading) == ("correct", "dispute")
    assert attempt.exercise_revision.lesson_revision.content_version == 1  # history untouched


def test_translation_station_options_and_next(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    options = client.get("/api/practice/translate/options").json()
    assert options == {"levels": ["A2"], "topics": []}  # factory exercises carry no grammar topics
    body = client.get("/api/practice/translate/next?level=A2&direction=en_fr").json()
    assert body["type"] == "translate" and body["lesson"]["id"] == "a2-passe-compose-er"
    assert "accepted_answers" not in body
    assert client.get("/api/practice/translate/next?direction=fr_en").status_code == 404


def test_progress_completion(client_user: tuple[Client, User]) -> None:
    client, _ = client_user
    assert (
        client.post(
            "/api/lessons/a2-passe-compose-er/progress", {}, content_type="application/json"
        ).json()["status"]
        == "in_progress"
    )
    done = client.post(
        "/api/lessons/a2-passe-compose-er/progress",
        {"completed": True},
        content_type="application/json",
    ).json()
    assert done["status"] == "completed" and done["completed_at"]
