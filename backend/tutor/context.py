"""Server-side tutor context: the browser sends IDs, the server decides what the model sees.
Everything here is budgeted so the prompt stays small (prefill time is part of the wait)."""

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db.models import Count
from django.utils import timezone

from accounts.models import LearnerProfile, User
from contentkit.models import BLANK
from contentkit.reference import Reference
from curriculum.models import ExerciseRevision, GrammarTopic, Lesson
from exercises.models import ExerciseAttempt, MistakeOccurrence
from progress.models import TopicMastery

MAX_SECTION_CHARS = 500


class ContextError(ValueError):
    pass


@dataclass
class TutorContext:
    ref: dict[str, Any]
    title: str
    text: str
    attempted: bool


def validate_ref(user: User, raw: Any) -> dict[str, Any]:
    """Keep only references that exist and belong to the user."""
    if raw in (None, {}):
        return {}
    if not isinstance(raw, dict):
        raise ContextError("context must be an object")
    ref: dict[str, Any] = {}
    if lesson_id := raw.get("lesson_id"):
        if not isinstance(lesson_id, str) or not Lesson.objects.filter(slug=lesson_id).exists():
            raise ContextError("unknown lesson")
        ref["lesson_id"] = lesson_id
    if (revision_id := raw.get("exercise_revision_id")) is not None:
        if (
            not isinstance(revision_id, int)
            or not ExerciseRevision.objects.filter(pk=revision_id).exists()
        ):
            raise ContextError("unknown exercise")
        ref["exercise_revision_id"] = revision_id
    if (attempt_id := raw.get("attempt_id")) is not None:
        if (
            not isinstance(attempt_id, int)
            or not ExerciseAttempt.objects.filter(pk=attempt_id, user=user).exists()
        ):
            raise ContextError("unknown attempt")
        ref["attempt_id"] = attempt_id
    return ref


def _lookup(
    user: User, ref: dict[str, Any]
) -> tuple[Lesson | None, ExerciseRevision | None, ExerciseAttempt | None]:
    """Resolve a context reference; the most specific item determines the others."""
    attempt = None
    if (attempt_id := ref.get("attempt_id")) is not None:
        attempt = (
            ExerciseAttempt.objects.select_related(
                "exercise_revision__lesson_revision__lesson__unit"
            )
            .filter(pk=attempt_id, user=user)
            .first()
        )
    revision = attempt.exercise_revision if attempt else None
    if revision is None and (revision_id := ref.get("exercise_revision_id")) is not None:
        revision = (
            ExerciseRevision.objects.select_related("lesson_revision__lesson__unit")
            .filter(pk=revision_id)
            .first()
        )
    lesson = revision.lesson_revision.lesson if revision else None
    if lesson is None and (lesson_id := ref.get("lesson_id")):
        lesson = (
            Lesson.objects.select_related("unit", "published_revision")
            .filter(slug=lesson_id)
            .first()
        )
    return lesson, revision, attempt


def thread_title(ref: dict[str, Any], user: User) -> str:
    lesson, revision, _ = _lookup(user, ref)
    if lesson and revision:
        return f"{lesson.title} · {revision.payload['id']}"
    return lesson.title if lesson else "General question"


def build_context(user: User, ref: dict[str, Any], question: str = "") -> TutorContext:
    profile = LearnerProfile.for_user(user)
    parts = [
        f"Learner: CEFR {profile.level}, aiming for {profile.target_level}; learning Québec French."
    ]
    lesson, revision, attempt = _lookup(user, ref)
    texts: list[str] = [question]
    payload = None
    if revision is not None:
        payload = revision.lesson_revision.payload
    elif lesson is not None and lesson.published_revision is not None:
        payload = lesson.published_revision.payload
    if lesson is not None and payload is not None:
        topic_slugs = payload.get("grammar_topics", [])
        topics = ", ".join(
            GrammarTopic.objects.filter(slug__in=topic_slugs).values_list("title", flat=True)
        )
        explanation = next(
            (s["body"] for s in payload["sections"] if s["type"] == "explanation"), ""
        )
        excerpt = explanation[:MAX_SECTION_CHARS]
        parts.append(
            f"Current lesson: {payload['title']} ({payload['title_en']}), {lesson.unit.level}.\n"
            f"Objectives: {'; '.join(payload['objectives'])}\nGrammar: {topics or 'none'}\n"
            f"Lesson explanation (excerpt): {excerpt}"
        )
        texts.append(excerpt)
    if revision is not None:
        description = _describe_exercise(revision.payload)
        parts.append("Current exercise:\n" + description)
        texts.append(description)
    if attempt is not None:
        fb = attempt.feedback
        errors = (
            "; ".join(
                f"{e['category']}: «{e.get('span', '')}» ({e.get('explanation', '')})"
                for e in fb.get("errors", [])
            )
            or "none"
        )
        parts.append(
            f"The learner answered: «{attempt.answer}». "
            f"Verdict: {attempt.verdict or 'not graded'}.\n"
            f"Errors found by the automatic grader (a smaller model; it can be wrong): {errors}\n"
            f"Suggested correction: {fb.get('corrected') or '-'}"
        )
        texts.append(attempt.answer)
    elif revision is not None:
        parts.append("The learner has NOT answered this exercise yet: give hints, not the answer.")
    parts += _learning_signals(user)
    ref_data = Reference.load(Path(settings.CONTENT_DIR))
    hint = _hint_verb(revision.payload) if revision is not None else None
    # Verbs come from what the learner is working on, not from the lesson prose.
    exercise_text = _describe_exercise(revision.payload) if revision is not None else ""
    answer = attempt.answer if attempt is not None else ""
    verbs = ([hint] if hint else []) + ref_data.verbs_in(answer, exercise_text, question)
    facts = [f for f in dict.fromkeys(ref_data.verb_facts(v) for v in verbs) if f]
    if facts:
        parts.append(
            "Verified verb facts (from the conjugation reference; authoritative):\n"
            + "\n".join(f"- {f}" for f in facts[:4])
        )
    lexicon = ref_data.quebec_terms_in(*texts)
    if lexicon:
        parts.append(
            "Verified Québec usage (authoritative):\n"
            + "\n".join(
                f"- {t.term}: {t.meaning} (France: {t.france}; {t.formality})" for t in lexicon
            )
        )
    return TutorContext(
        ref=ref,
        title=thread_title(ref, user),
        text="\n\n".join(parts),
        attempted=attempt is not None,
    )


def _describe_exercise(payload: dict[str, Any]) -> str:
    kind = payload["type"]
    if kind == "translate":
        direction = "English → French" if payload["direction"] == "en_fr" else "French → English"
        return (
            f"Translate ({direction}): «{payload['prompt']}». "
            f"Accepted answers: {' | '.join(payload['accepted_answers'])}"
        )
    if kind == "fill_blank":
        filled = payload["sentence"].replace(BLANK, payload["answers"][0])
        return (
            f"Fill in the blank: «{payload['sentence']}» {payload.get('hint') or ''}. "
            f"Answer: {' / '.join(payload['answers'])} → «{filled}»"
        )
    options = " | ".join(f"{i}) {o}" for i, o in enumerate(payload["options"]))
    return (
        f"Multiple choice: {payload['question']} Options: {options}. "
        f"Correct: option {payload['answer_index']}. {payload.get('explanation', '')}"
    )


def _learning_signals(user: User) -> list[str]:
    since = timezone.now() - timedelta(days=30)
    recurring = (
        MistakeOccurrence.objects.filter(attempt__user=user, created_at__gte=since)
        .values("category")
        .annotate(n=Count("id"))
        .order_by("-n")[:3]
    )
    weak = (
        TopicMastery.objects.filter(user=user, attempts__gte=3)
        .order_by("ewma")
        .select_related("topic")[:3]
    )
    out = []
    if recurring:
        out.append(
            "Recurring mistakes (last 30 days): "
            + ", ".join(f"{r['category']} ×{r['n']}" for r in recurring)
        )
    if weak:
        out.append("Weakest topics: " + ", ".join(f"{m.topic.title} ({m.ewma:.0%})" for m in weak))
    return out


def _hint_verb(payload: dict[str, Any]) -> str | None:
    hint = (payload.get("hint") or "").strip().strip("()").strip()
    return (
        hint if re.fullmatch(r"(se |s')?[a-zàâçéèêëîïôûùüÿœ-]+(er|ir|re|oir)", hint, re.I) else None
    )
