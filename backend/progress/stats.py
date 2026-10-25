"""Dashboard numbers, computed on request from the activity tables (no extra bookkeeping).

A study day is a local calendar day (settings.TIME_ZONE) with at least one graded exercise,
verb drill answer or vocabulary review. Study time is the time spent on those items, each
capped so a tab left open does not count as an hour of study; lesson reading is not timed."""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from django.db.models import Count, Q
from django.utils import timezone

from accounts.models import User
from contentkit.conjugation import TENSE_BY_KEY
from curriculum.models import Lesson
from exercises.models import ExerciseAttempt, MistakeOccurrence
from verbs.models import ConjugationAttempt, VerbMastery
from vocabulary import services as vocab
from vocabulary.models import VocabReview

from .models import LessonProgress, ReviewSet, TopicMastery
from .review import current_set, weak_topics

ITEM_CAP_MS = 3 * 60 * 1000
HISTORY_DAYS = 14
MISTAKE_DAYS = 30


@dataclass
class Day:
    items: int = 0
    correct: int = 0
    graded: int = 0
    ms: int = 0
    kinds: Counter[str] = field(default_factory=Counter)


def _local(moment: datetime) -> date:
    return timezone.localtime(moment).date()


def _activity(user: User, since: datetime | None) -> dict[date, Day]:
    """Per-day activity; `since=None` reads only timestamps (for the streak)."""
    days: dict[date, Day] = defaultdict(Day)

    def add(kind: str, moment: datetime, ms: int | None, correct: bool | None) -> None:
        day = days[_local(moment)]
        day.items += 1
        day.kinds[kind] += 1
        day.ms += min(ms or 0, ITEM_CAP_MS)
        if correct is not None:
            day.graded += 1
            day.correct += correct

    window = {} if since is None else {"created_at__gte": since}
    for moment, ms, verdict in ExerciseAttempt.objects.filter(
        user=user, status=ExerciseAttempt.Status.GRADED, **window
    ).values_list("created_at", "time_spent_ms", "verdict"):
        add("exercises", moment, ms, verdict != ExerciseAttempt.Verdict.INCORRECT)
    for moment, ms, result in ConjugationAttempt.objects.filter(user=user, **window).values_list(
        "created_at", "time_spent_ms", "result"
    ):
        add("verbs", moment, ms, result != ConjugationAttempt.Result.INCORRECT)
    reviews = VocabReview.objects.filter(card__user=user)
    if since is not None:
        reviews = reviews.filter(reviewed_at__gte=since)
    for moment, ms in reviews.values_list("reviewed_at", "duration_ms"):
        add("vocab", moment, ms, None)  # self-rated: not counted towards accuracy
    return days


def streak(active: set[date], today: date) -> dict[str, Any]:
    """Consecutive study days ending today, or yesterday if today has no study yet."""
    current = 0
    cursor = today if today in active else today - timedelta(days=1)
    while cursor in active:
        current += 1
        cursor -= timedelta(days=1)
    longest = run = 0
    previous: date | None = None
    for day in sorted(active):
        run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    return {"current": current, "longest": longest, "studied_today": today in active}


def dashboard(user: User) -> dict[str, Any]:
    now = timezone.now()
    today = _local(now)
    start = timezone.make_aware(
        datetime.combine(today - timedelta(days=HISTORY_DAYS - 1), datetime.min.time())
    )
    recent = _activity(user, start)
    week = [today - timedelta(days=i) for i in range(7)]
    graded = sum(recent[d].graded for d in week if d in recent)
    correct = sum(recent[d].correct for d in week if d in recent)

    topics = [
        {
            "id": m.topic_id,
            "title": m.topic.title,
            "level": m.topic.level,
            "attempts": m.attempts,
            "accuracy": round(m.ewma, 3),
            "last_practiced": m.last_practiced.isoformat() if m.last_practiced else None,
        }
        for m in TopicMastery.objects.filter(user=user, attempts__gt=0)
        .select_related("topic")
        .order_by("ewma", "topic__slug")
    ]
    tenses: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
    for m in VerbMastery.objects.filter(user=user, attempts__gt=0):
        tenses[m.tense][0] += m.attempts
        tenses[m.tense][1] += m.ewma * m.attempts
    mistakes = (
        MistakeOccurrence.objects.filter(
            attempt__user=user, created_at__gte=now - timedelta(days=MISTAKE_DAYS)
        )
        .values("category")
        .annotate(count=Count("id"))
        .order_by("-count", "category")[:6]
    )
    lessons = Lesson.objects.filter(published_revision__isnull=False)
    review = current_set(user)
    return {
        "today": today.isoformat(),
        "streak": streak(set(_activity(user, None)), today),
        "minutes": {
            "today": round(recent[today].ms / 60000) if today in recent else 0,
            "week": round(sum(recent[d].ms for d in week if d in recent) / 60000),
        },
        "accuracy_week": {
            "graded": graded,
            "accuracy": round(correct / graded, 3) if graded else None,
        },
        "history": [
            {
                "date": d.isoformat(),
                "items": recent[d].items if d in recent else 0,
                "minutes": round(recent[d].ms / 60000) if d in recent else 0,
                "by_kind": dict(recent[d].kinds) if d in recent else {},
            }
            for d in (today - timedelta(days=i) for i in reversed(range(HISTORY_DAYS)))
        ],
        "lessons": {
            "published": lessons.count(),
            "completed": LessonProgress.objects.filter(
                user=user, status=LessonProgress.Status.COMPLETED, lesson__in=lessons
            ).count(),
        },
        "vocab": vocab.stats(user),
        "topics": topics,
        "weak_topics": [w.as_dict() for w in weak_topics(user)],
        "verb_tenses": sorted(
            (
                {
                    "tense": t,
                    "label": TENSE_BY_KEY[t].label if t in TENSE_BY_KEY else t,
                    "attempts": n,
                    "accuracy": round(s / n, 3),
                }
                for t, (n, s) in tenses.items()
            ),
            key=lambda x: x["accuracy"],
        ),
        "mistakes": list(mistakes),
        "review": None if review is None else review_summary(review),
    }


def review_summary(review: ReviewSet) -> dict[str, Any]:
    items = review.items.count()
    done = (
        review.items.filter(
            Q(exercise_revision__attempts__user=review.user)
            & Q(exercise_revision__attempts__created_at__gte=review.created_at)
        )
        .distinct()
        .count()
    )
    return {"id": review.pk, "items": items, "answered": done, "extras": review.extras}
