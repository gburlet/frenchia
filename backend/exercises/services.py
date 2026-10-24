"""Attempt lifecycle: grade -> record -> mistakes + mastery; regrade; dispute; accept answer."""

from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from accounts.models import User
from authoring.writer import HEADER, ContentWriter
from contentkit.models import Lesson as LessonContent
from contentkit.reference import Reference
from contentkit.yamlio import dump_yaml, to_data, write_text_atomic
from curriculum.importer import import_content
from curriculum.models import ExerciseRevision, GrammarTopic
from inference.providers import get_chat_model
from progress.models import LessonProgress, TopicMastery

from .grading import PROMPT_VERSION, Grade, grade_choice, grade_fill_blank, grade_translate
from .models import ExerciseAttempt, MistakeOccurrence

EWMA_WEIGHT = 0.3  # weight of the newest attempt in TopicMastery.ewma


class AttemptError(Exception):
    pass


def _reference() -> Reference:
    return Reference.load(Path(settings.CONTENT_DIR))


def grade(revision: ExerciseRevision, answer: Any) -> Grade:
    payload = revision.payload
    kind = payload["type"]
    if kind in ("multiple_choice", "comprehension"):
        if (
            not isinstance(answer, int)
            or isinstance(answer, bool)
            or not 0 <= answer < len(payload["options"])
        ):
            raise AttemptError("answer must be the index of an option")
        return grade_choice(payload, answer)
    if not isinstance(answer, str) or not answer.strip():
        raise AttemptError("answer must be non-empty text")
    if len(answer) > 500:
        raise AttemptError("answer is too long")
    if kind == "fill_blank":
        return grade_fill_blank(payload, answer)
    level = revision.lesson_revision.lesson.unit.level
    return grade_translate(payload, answer, level=level, chat=get_chat_model(), ref=_reference())


def submit_attempt(
    user: User, revision: ExerciseRevision, answer: Any, time_spent_ms: int | None
) -> ExerciseAttempt:
    result = grade(revision, answer)
    with transaction.atomic():
        attempt = ExerciseAttempt.objects.create(
            user=user,
            exercise_revision=revision,
            answer=str(answer),
            prompt_snapshot=revision.payload,
            time_spent_ms=time_spent_ms,
            **_fields(result),
        )
        LessonProgress.objects.get_or_create(user=user, lesson=revision.lesson_revision.lesson)
        if result.status == "graded":
            _record_learning(attempt)
    return attempt


def regrade(attempt: ExerciseAttempt) -> ExerciseAttempt:
    if attempt.status != ExerciseAttempt.Status.PENDING:
        return attempt
    answer: Any = attempt.answer
    if attempt.prompt_snapshot["type"] in ("multiple_choice", "comprehension"):
        answer = int(answer)
    result = grade(attempt.exercise_revision, answer)
    with transaction.atomic():
        for key, value in _fields(result).items():
            setattr(attempt, key, value)
        attempt.save()
        if result.status == "graded":
            _record_learning(attempt)
    return attempt


def _fields(result: Grade) -> dict[str, Any]:
    return {
        "status": result.status,
        "grading": result.grading,
        "verdict": result.verdict or "",
        "score": result.score,
        "feedback": result.feedback,
        "model": result.model,
        "latency_ms": result.latency_ms,
        "prompt_version": PROMPT_VERSION if result.grading == "llm" else "",
        "graded_at": timezone.now() if result.status == "graded" else None,
    }


def _record_learning(attempt: ExerciseAttempt) -> None:
    # Exercises without their own topics practise the lesson's.
    topic_ids = (
        attempt.prompt_snapshot.get("grammar_topics")
        or attempt.exercise_revision.lesson_revision.payload.get("grammar_topics")
        or []
    )
    topics = list(GrammarTopic.objects.filter(slug__in=topic_ids))
    primary = topics[0] if topics else None
    for error in attempt.feedback.get("errors", []):
        if error.get("severity") == "error":
            MistakeOccurrence.objects.create(
                attempt=attempt,
                category=error["category"],
                grammar_topic=primary,
                span=error.get("span", "")[:300],
                explanation=error.get("explanation", ""),
            )
    score = (attempt.score or 0) / 100
    for topic in topics:
        mastery, _ = TopicMastery.objects.select_for_update().get_or_create(
            user=attempt.user, topic=topic
        )
        mastery.ewma = (
            score
            if mastery.attempts == 0
            else (1 - EWMA_WEIGHT) * mastery.ewma + EWMA_WEIGHT * score
        )
        mastery.attempts += 1
        mastery.correct += attempt.verdict != ExerciseAttempt.Verdict.INCORRECT
        mastery.last_practiced = timezone.now()
        mastery.save()


def dispute(attempt: ExerciseAttempt, comment: str) -> None:
    attempt.disputed = True
    attempt.dispute_comment = comment[:1000]
    attempt.save(update_fields=["disputed", "dispute_comment"])


def accept_disputed_answer(attempt: ExerciseAttempt) -> Path:
    """Add the learner's answer to the exercise's accepted answers in the lesson file (a new
    content version, imported and published) and mark the attempt correct. The file change is
    a human edit, so it is detected as one; commit it with git like any content change."""
    kind = attempt.prompt_snapshot["type"]
    field = {"translate": "accepted_answers", "fill_blank": "answers"}.get(kind)
    if field is None:
        raise AttemptError("only translation and fill-in-the-blank answers can be accepted")
    writer = ContentWriter(Path(settings.CONTENT_DIR))
    lesson = attempt.exercise_revision.lesson_revision.lesson
    path = writer.root / "lessons" / lesson.level.lower() / f"{lesson.slug}.yaml"
    current = writer.read_lesson(path)
    if current is None:
        raise AttemptError(f"{path.name} not found")
    data = current.model_dump(mode="json", exclude_none=True)
    exercise_id = attempt.prompt_snapshot["id"]
    target = next(
        (e for e in data["exercises"] if e["id"] == exercise_id and e["type"] == kind), None
    )
    if target is None:
        raise AttemptError(f"exercise {exercise_id} no longer exists in the current lesson")
    answer = attempt.answer.strip()
    if answer.casefold() not in {a.casefold() for a in target[field]}:
        target[field] = [*target[field], answer]
    data["content_version"] = current.content_version + 1
    updated = LessonContent.model_validate(data)
    previous = path.read_text(encoding="utf-8")
    write_text_atomic(path, HEADER + dump_yaml(to_data(updated)))
    result = import_content(writer.root, only={lesson.slug}, publish=True)
    if result.refused:
        write_text_atomic(path, previous)
        raise AttemptError("import refused: " + "; ".join(result.refused))
    attempt.verdict, attempt.score = ExerciseAttempt.Verdict.CORRECT, 100
    attempt.grading, attempt.dispute_resolved_at = ExerciseAttempt.Grading.DISPUTE, timezone.now()
    attempt.save(update_fields=["verdict", "score", "grading", "dispute_resolved_at"])
    return path
