"""What the browser may see of an exercise: everything except the answers."""

from typing import Any

from contentkit.models import BLANK
from curriculum.models import ExerciseRevision

from .models import ExerciseAttempt

HIDDEN = {"accepted_answers", "answers", "answer_index", "explanation", "grammar_topics"}


def public_exercise(revision: ExerciseRevision) -> dict[str, Any]:
    payload = {k: v for k, v in revision.payload.items() if k not in HIDDEN}
    return {"exercise_revision_id": revision.pk, **payload}


def attempt_result(attempt: ExerciseAttempt) -> dict[str, Any]:
    snap = attempt.prompt_snapshot
    kind = snap["type"]
    correct_answer: str | None
    accepted: list[str] = []
    correct_index: int | None = None
    if kind in ("multiple_choice", "comprehension"):
        correct_index = snap["answer_index"]
        correct_answer = snap["options"][correct_index]
    elif kind == "fill_blank":
        accepted = list(snap["answers"])
        correct_answer = snap["sentence"].replace(BLANK, accepted[0])
    else:
        accepted = list(snap["accepted_answers"])
        correct_answer = accepted[0]
    return {
        "attempt_id": attempt.pk,
        "status": attempt.status,
        "verdict": attempt.verdict or None,
        "score": attempt.score,
        "grading": attempt.grading,
        "correct_answer": correct_answer,
        "accepted_answers": accepted,
        "correct_index": correct_index,
        "feedback": attempt.feedback,
        "explanation": snap.get("explanation"),
        "model": attempt.model or None,
        "disputed": attempt.disputed,
    }
