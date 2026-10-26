"""AI critic: the local LLM proof-reads every French sentence a learner will be graded
against (filled-in blanks, French accepted answers, French prompts) using the judge-v2 design
from ADR 0002. Findings are *warnings* for the human reviewer, never verdicts."""

import re
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel

from contentkit.models import (
    BLANK,
    ComprehensionExercise,
    FillBlankExercise,
    Lesson,
    MultipleChoiceExercise,
    ReadingSection,
    TranslateExercise,
)
from contentkit.validate import Issue
from inference.errors import InvalidOutput
from inference.llm import ChatModel, Message, complete_structured

from . import prompts


class Finding(BaseModel):
    severity: Literal["error", "minor"]
    span: str
    explanation: str


class BlankCheck(BaseModel):
    other_accepted_answers: list[str]
    tests_the_lesson_point: bool
    problem: str


class Solution(BaseModel):
    correct_options: list[int]


class Critique(BaseModel):
    # An explicit verdict first: gpt-oss otherwise files "None, the sentence is correct" as an
    # error entry.
    correct: bool
    errors: list[Finding]


def _fill(sentence: str, answer: str) -> str:
    """The sentence as a learner reads it once filled: an elided answer (« l' ») joins the next
    word, so « ___ ai laissé » reads « l'ai laissé », not « l' ai »."""
    filled = sentence.replace(BLANK, answer)
    return re.sub(r"(\b\w['’]) (?=\w)", r"\1", filled) if answer.endswith(("'", "’")) else filled


def sentences_to_check(lesson: Lesson) -> list[tuple[str, str]]:
    """(exercise id, French sentence) pairs a learner is graded against."""
    out: list[tuple[str, str]] = []
    for ex in lesson.exercises:
        if isinstance(ex, FillBlankExercise):
            out += [(ex.id, _fill(ex.sentence, answer)) for answer in ex.answers]
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
        try:
            result, completion = complete_structured(chat, messages, Critique, max_tokens=400)
        except InvalidOutput:  # one unreadable check must not sink the whole job
            continue
        if record:
            record(completion.latency_ms / 1000, completion.completion_tokens or 0)
        if result.correct:
            continue
        for finding in result.errors:
            if finding.severity == "error" and finding.span.strip():
                issues.append(
                    Issue(
                        "warning",
                        f"{lesson.id}:{exercise_id}",
                        f"AI critic on {sentence!r}: {finding.span!r}: {finding.explanation}",
                    )
                )
    return issues


def solve_choices(
    chat: ChatModel, lesson: Lesson, record: Callable[[float, int], None] | None = None
) -> list[Issue]:
    """Answer every multiple-choice and comprehension question without its key: a key the
    model doesn't reach, or a second correct option, is flagged (AI critic warning). Wrong
    keys were the commonest error in generated lessons, and the sentence critic can't see
    them."""
    passages = {s.id: s.passage_fr for s in lesson.sections if isinstance(s, ReadingSection)}
    issues: list[Issue] = []
    for ex in lesson.exercises:
        if not isinstance(ex, MultipleChoiceExercise | ComprehensionExercise):
            continue
        passage = passages.get(ex.reading_id, "") if isinstance(ex, ComprehensionExercise) else ""
        options = "\n".join(f"{i}: {o}" for i, o in enumerate(ex.options))
        messages = [
            Message("system", prompts.SYSTEM),
            Message(
                "user",
                prompts.SOLVE.format(
                    level=lesson.level,
                    passage=f"Reading passage:\n{passage}\n\n" if passage else "",
                    question=ex.question,
                    options=options,
                ),
            ),
        ]
        try:
            result, completion = complete_structured(chat, messages, Solution, max_tokens=200)
        except InvalidOutput:
            continue
        if record:
            record(completion.latency_ms / 1000, completion.completion_tokens or 0)
        chosen = sorted(set(result.correct_options))
        if chosen != [ex.answer_index]:
            issues.append(
                Issue(
                    "warning",
                    f"{lesson.id}:{ex.id}",
                    f"AI critic solved the question: correct option(s) {chosen}, but the key is "
                    f"{ex.answer_index} (options are numbered from 0). Make exactly one option "
                    "correct and the key point to it.",
                )
            )
    return issues


def check_blanks(
    chat: ChatModel,
    lesson: Lesson,
    objectives: list[str],
    record: Callable[[float, int], None] | None = None,
) -> list[Issue]:
    """For each fill-in-the-blank: would a teacher accept an answer the key lacks (« Je ___ dis
    la vérité » fits any pronoun), and does the blank practise the lesson's point? A blank
    whose answer is « au chalet » in a lesson on « y » does neither."""
    issues: list[Issue] = []
    for ex in lesson.exercises:
        if not isinstance(ex, FillBlankExercise):
            continue
        messages = [
            Message("system", prompts.SYSTEM),
            Message(
                "user",
                prompts.CHECK_BLANK.format(
                    level=lesson.level,
                    objectives="; ".join(objectives) or lesson.title,
                    sentence=ex.sentence,
                    hint=ex.hint or "(none)",
                    answers=" / ".join(ex.answers),
                ),
            ),
        ]
        try:
            result, completion = complete_structured(chat, messages, BlankCheck, max_tokens=300)
        except InvalidOutput:
            continue
        if record:
            record(completion.latency_ms / 1000, completion.completion_tokens or 0)
        keyed = {_key(a) for a in ex.answers}
        others = [a for a in result.other_accepted_answers if _key(a) not in keyed]
        if others or not result.tests_the_lesson_point:
            what = []
            if others:
                what.append(f"a teacher would also accept {others}")
            if not result.tests_the_lesson_point:
                what.append("the blank does not practise the lesson's point")
            issues.append(
                Issue(
                    "warning",
                    f"{lesson.id}:{ex.id}",
                    f"AI critic on the blank {ex.sentence!r} (key {ex.answers}): "
                    f"{'; '.join(what)}. {result.problem}".strip(),
                )
            )
    return issues


def _key(answer: str) -> str:
    return " ".join(answer.casefold().replace("’", "'").split())
