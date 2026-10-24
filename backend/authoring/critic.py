"""AI critic: the local LLM proof-reads every French sentence a learner will be graded
against (filled-in blanks, French accepted answers, French prompts) using the judge-v2 design
from ADR 0002. Findings are *warnings* for the human reviewer, never verdicts."""

from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from contentkit.models import BLANK, FillBlankExercise, Lesson, TranslateExercise
from contentkit.validate import Issue
from inference.llm import ChatModel, Message, complete_structured

from . import prompts


class Finding(BaseModel):
    severity: Literal["error", "minor"]
    span: str
    explanation: str


class Critique(BaseModel):
    errors: list[Finding]


def sentences_to_check(lesson: Lesson) -> list[tuple[str, str]]:
    """(exercise id, French sentence) pairs a learner is graded against."""
    out: list[tuple[str, str]] = []
    for ex in lesson.exercises:
        if isinstance(ex, FillBlankExercise):
            out += [(ex.id, ex.sentence.replace(BLANK, answer)) for answer in ex.answers]
        elif isinstance(ex, TranslateExercise):
            out += (
                [(ex.id, a) for a in ex.accepted_answers]
                if ex.direction == "en_fr"
                else [(ex.id, ex.prompt)]
            )
    return out


def critique(
    chat: ChatModel, lesson: Lesson, record: Callable[[float, int], None] | None = None
) -> list[Issue]:
    issues: list[Issue] = []
    for exercise_id, sentence in sentences_to_check(lesson):
        messages = [
            Message("system", prompts.SYSTEM),
            Message("user", prompts.CRITIC.format(level=lesson.level, sentence=sentence)),
        ]
        result, completion = complete_structured(chat, messages, Critique, max_tokens=400)
        if record:
            record(completion.latency_ms / 1000, completion.completion_tokens or 0)
        for finding in result.errors:
            if finding.severity == "error":
                issues.append(
                    Issue(
                        "warning",
                        f"{lesson.id}:{exercise_id}",
                        f"AI critic on {sentence!r}: {finding.span!r}: {finding.explanation}",
                    )
                )
    return issues
