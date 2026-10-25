"""Rules-based review sets (Phase 7).

Weak topics come from TopicMastery (recent-weighted accuracy) and recent MistakeOccurrences.
A set is built immediately from published curriculum exercises on those topics, so it never
waits for the LLM; exercises the local LLM writes around the learner's mistakes are added in
the background (queue "practice") and labelled AI-generated."""

import logging
import traceback
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.db import transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from accounts.models import User
from contentkit.models import Lesson as LessonContent
from contentkit.yamlio import content_hash
from curriculum import content
from curriculum.models import Exercise, ExerciseRevision, GrammarTopic, Lesson
from exercises.models import ExerciseAttempt, MistakeOccurrence
from inference.providers import get_chat_model

from .models import ReviewItem, ReviewSet, TopicMastery

logger = logging.getLogger(__name__)

WEAK_EWMA = 0.8  # below this recent-weighted accuracy a topic needs review
MIN_ATTEMPTS = 2  # ...once it has been tried at least this often
MISTAKE_WINDOW = timedelta(days=21)
MAX_TOPICS = 3
SET_SIZE = 9  # curriculum items; fewer weak topics get more items each
PER_TOPIC_MAX = 6
GENERATED_TOPICS = 2  # the LLM writes extras for this many of the weakest topics
REVIEWABLE = ("fill_blank", "translate", "multiple_choice")  # comprehension needs its passage


class ReviewUnavailable(Exception):
    pass


@dataclass
class WeakTopic:
    topic: GrammarTopic
    ewma: float | None
    attempts: int
    mistakes: int

    @property
    def score(self) -> float:
        """Higher = weaker. Untried mastery counts as middling."""
        return (1 - (self.ewma if self.ewma is not None else 0.5)) + 0.1 * min(self.mistakes, 5)

    @property
    def reason(self) -> str:
        parts = []
        if self.ewma is not None and self.attempts >= MIN_ATTEMPTS:
            parts.append(f"{round(self.ewma * 100)}% recent accuracy over {self.attempts} tries")
        if self.mistakes:
            parts.append(f"{self.mistakes} mistake{'s' * (self.mistakes > 1)} in the last 3 weeks")
        return "; ".join(parts) or "not practised much yet"

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.topic.slug,
            "title": self.topic.title,
            "level": self.topic.level,
            "accuracy": None if self.ewma is None else round(self.ewma, 3),
            "attempts": self.attempts,
            "recent_mistakes": self.mistakes,
            "reason": self.reason,
        }


def weak_topics(user: User, limit: int = MAX_TOPICS) -> list[WeakTopic]:
    since = timezone.now() - MISTAKE_WINDOW
    mistakes = Counter(
        MistakeOccurrence.objects.filter(
            attempt__user=user, created_at__gte=since, grammar_topic__isnull=False
        ).values_list("grammar_topic", flat=True)
    )
    mastery = {m.topic_id: m for m in TopicMastery.objects.filter(user=user)}
    slugs = set(mistakes) | {
        slug for slug, m in mastery.items() if m.attempts >= MIN_ATTEMPTS and m.ewma < WEAK_EWMA
    }
    found = [
        WeakTopic(
            topic=topic,
            ewma=mastery[topic.slug].ewma if topic.slug in mastery else None,
            attempts=mastery[topic.slug].attempts if topic.slug in mastery else 0,
            mistakes=mistakes.get(topic.slug, 0),
        )
        for topic in GrammarTopic.objects.filter(slug__in=slugs)
    ]
    return sorted(found, key=lambda w: (-w.score, w.topic.slug))[:limit]


def _fallback_topics(user: User, limit: int) -> list[WeakTopic]:
    """No weak spots yet: review the topics of lessons the learner has opened, least practised
    first."""
    slugs: list[str] = []
    for lesson in Lesson.objects.filter(
        progress__user=user, published_revision__isnull=False
    ).select_related("published_revision"):
        assert lesson.published_revision is not None
        slugs += lesson.published_revision.payload.get("grammar_topics", [])
    mastery = {m.topic_id: m for m in TopicMastery.objects.filter(user=user, topic__in=slugs)}
    topics = sorted(
        GrammarTopic.objects.filter(slug__in=slugs),
        key=lambda t: (mastery[t.slug].attempts if t.slug in mastery else 0, t.slug),
    )
    return [
        WeakTopic(
            t,
            mastery[t.slug].ewma if t.slug in mastery else None,
            mastery[t.slug].attempts if t.slug in mastery else 0,
            0,
        )
        for t in topics[:limit]
    ]


def _candidates(user: User, topic: str) -> list[tuple[ExerciseRevision, str]]:
    """Published curriculum exercises (and this learner's earlier AI-generated ones) on
    `topic`, best first: answered wrong last time, never tried, then least recently tried."""
    revisions = ExerciseRevision.objects.filter(
        Q(origin=ExerciseRevision.Origin.CURRICULUM)
        | Q(origin=ExerciseRevision.Origin.PERSONALIZED, review_items__review_set__user=user),
        # Exercises without their own topics practise the lesson's (as in exercises.services).
        Q(payload__grammar_topics__contains=[topic])
        | (
            (Q(payload__grammar_topics=[]) | ~Q(payload__has_key="grammar_topics"))
            & Q(lesson_revision__payload__grammar_topics__contains=[topic])
        ),
        lesson_revision__lesson__published_revision=F("lesson_revision"),
        payload__type__in=REVIEWABLE,
    ).distinct()
    history: dict[str, tuple[Any, str]] = {}
    for exercise_id, created, verdict in (
        ExerciseAttempt.objects.filter(user=user, exercise_revision__in=revisions)
        .order_by("created_at")
        .values_list("exercise_revision__exercise", "created_at", "verdict")
    ):
        history[exercise_id] = (created, verdict)  # the latest attempt wins
    ranked: list[tuple[tuple[int, Any], ExerciseRevision, str]] = []
    for revision in revisions:
        last = history.get(revision.exercise_id)
        if last is None:
            ranked.append(((1, revision.pk), revision, ReviewItem.Source.UNSEEN))
        elif last[1] == ExerciseAttempt.Verdict.INCORRECT:
            ranked.append(((0, last[0]), revision, ReviewItem.Source.MISSED))
        else:
            ranked.append(((2, last[0]), revision, ReviewItem.Source.REFRESH))
    ranked.sort(key=lambda r: r[0])
    return [(revision, source) for _, revision, source in ranked]


def current_set(user: User) -> ReviewSet | None:
    return ReviewSet.objects.filter(user=user, completed_at__isnull=True).first()


@transaction.atomic
def build_set(user: User, *, generate: bool = True) -> ReviewSet:
    """Start a new review set (an unfinished one is closed first)."""
    ReviewSet.objects.filter(user=user, completed_at__isnull=True).update(
        completed_at=timezone.now()
    )
    weak = weak_topics(user) or _fallback_topics(user, MAX_TOPICS)
    picks: list[tuple[ExerciseRevision, GrammarTopic, str]] = []
    used: set[int] = set()
    per_topic = min(PER_TOPIC_MAX, -(-SET_SIZE // max(1, len(weak))))
    for w in weak:
        chosen = [(r, s) for r, s in _candidates(user, w.topic.slug) if r.pk not in used]
        for revision, source in chosen[:per_topic]:
            used.add(revision.pk)
            picks.append((revision, w.topic, source))
    if not picks:
        raise ReviewUnavailable(
            "Nothing to review yet: practise a lesson's exercises first, then come back."
        )
    review = ReviewSet.objects.create(user=user, topics=[w.as_dict() for w in weak])
    ReviewItem.objects.bulk_create(
        ReviewItem(review_set=review, order=i, exercise_revision=r, topic=t, source=s)
        for i, (r, t, s) in enumerate(picks)
    )
    if generate and _lesson_for(weak[0].topic.slug) is not None:
        review.extras = ReviewSet.Extras.QUEUED
        review.save(update_fields=["extras"])
        from .tasks import generate_review_extras

        transaction.on_commit(lambda: generate_review_extras.enqueue(review.pk))
    return review


def _lesson_for(topic: str) -> Lesson | None:
    """The published lesson that teaches `topic` (the most recently ordered one)."""
    return (
        Lesson.objects.filter(
            published_revision__isnull=False,
            published_revision__payload__grammar_topics__contains=[topic],
        )
        .select_related("unit", "published_revision")
        .order_by("-order")
        .first()
    )


def _mistakes(user: User, topic: str, limit: int = 8) -> list[str]:
    rows = (
        MistakeOccurrence.objects.filter(attempt__user=user, grammar_topic=topic)
        .select_related("attempt")
        .order_by("-created_at")[:limit]
    )
    return [
        f"wrote « {m.attempt.answer[:120]} »: {m.category}"
        + (f" ({m.span[:60]})" if m.span else "")
        + (f": {m.explanation[:160]}" if m.explanation else "")
        for m in rows
    ]


def generate_extras(review_id: int) -> ReviewSet:
    """Background step: add LLM-written exercises for the weakest topics to a review set."""
    from authoring.practice import PracticeGenerator
    from authoring.services import brief_for

    review = ReviewSet.objects.select_related("user").get(pk=review_id)
    if review.extras != ReviewSet.Extras.QUEUED:
        return review
    review.extras = ReviewSet.Extras.RUNNING
    review.save(update_fields=["extras"])
    log: list[dict[str, Any]] = []
    try:
        ref = content.reference()
        chat = get_chat_model()
        for entry in review.topics[:GENERATED_TOPICS]:
            lesson = _lesson_for(entry["id"])
            if lesson is None or lesson.published_revision is None:
                continue
            published = LessonContent.model_validate(lesson.published_revision.payload)
            result = PracticeGenerator(chat, ref).practice(
                brief_for(lesson), published, entry["id"], _mistakes(review.user, entry["id"])
            )
            _attach(review, lesson, entry["id"], result.exercises)
            log.append(
                {
                    "topic": entry["id"],
                    "lesson": lesson.slug,
                    "kept": len(result.exercises),
                    "dropped": [f"{i.path}: {i.message}" for i in result.dropped],
                    "llm_calls": result.stats.calls,
                    "llm_seconds": round(result.stats.seconds, 1),
                }
            )
        review.extras = ReviewSet.Extras.READY
    except Exception as exc:
        logger.exception("Review set %s: generating extras failed", review.pk)
        review.extras = ReviewSet.Extras.FAILED
        review.extras_error = f"{exc}\n\n{traceback.format_exc()}"
    review.extras_log = log
    review.save(update_fields=["extras", "extras_error", "extras_log"])
    return review


@transaction.atomic
def _attach(review: ReviewSet, lesson: Lesson, topic: str, exercises: list[Any]) -> None:
    revision = lesson.published_revision
    assert revision is not None
    start = (review.items.aggregate(n=Max("order"))["n"] or 0) + 1
    for i, exercise in enumerate(exercises):
        data = exercise.model_dump(mode="json", exclude_none=True)
        row = Exercise.objects.create(
            stable_id=f"{lesson.slug}/review-{review.pk}-{exercise.id}",
            lesson=lesson,
            kind=exercise.type,
        )
        ExerciseRevision.objects.create(
            exercise=row,
            lesson_revision=revision,
            content_hash=content_hash(exercise),
            payload=data,
            origin=ExerciseRevision.Origin.PERSONALIZED,
        )
        ReviewItem.objects.create(
            review_set=review,
            order=start + i,
            exercise_revision=row.revisions.get(),
            topic_id=topic,
            source=ReviewItem.Source.GENERATED,
        )
