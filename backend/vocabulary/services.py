"""Vocabulary Station: spaced repetition (FSRS) over word cards, and deterministic checking of
typed recall answers (word, accents, article and gender)."""

import re
from datetime import datetime, timedelta
from typing import Any, Literal

from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.utils import timezone
from fsrs import Card, Rating, Scheduler

from accounts.models import LearnerProfile, User
from contentkit.conjugation import strip_accents
from contentkit.reference import normalize

from .models import Lexeme, VocabCard, VocabReview, VocabSet

SCHEDULER = Scheduler(desired_retention=0.9, enable_fuzzing=True)
PREVIEW = Scheduler(desired_retention=0.9, enable_fuzzing=False)
LEARN_AHEAD = timedelta(minutes=20)

# Words starting with an aspirated h take le/la, not l' (le hockey, la hache).
H_ASPIRE = frozenset(
    "hache haie hall hamac hamburger hameau hanche handicap hangar hareng haricot harpe hasard "
    "hâte hausse haut hauteur héron héros hérisson hibou hockey homard honte hublot huard huit "
    "hurlement hutte halloween".split()
)
VOWELS = "aeiouyéèêëàâîïôûùœæ"

CheckResult = Literal["correct", "accent", "article", "gender", "incorrect"]
SUGGESTED: dict[str, int] = {"correct": 3, "accent": 2, "article": 2, "gender": 1, "incorrect": 1}


# --- display and checking ------------------------------------------------------------------


def article(lexeme: Lexeme) -> str:
    """Definite article as written before the word: le, la or l'."""
    if lexeme.pos != "noun" or lexeme.gender not in ("m", "f"):
        return ""
    first = normalize(lexeme.fr)
    if first[:1] in VOWELS or (first[:1] == "h" and first.split()[0] not in H_ASPIRE):
        return "l'"
    return "le" if lexeme.gender == "m" else "la"


def display(lexeme: Lexeme) -> str:
    """la pomme, l'arbre, le hockey; other parts of speech unchanged."""
    art = article(lexeme)
    return f"{art}{lexeme.fr}" if art == "l'" else f"{art} {lexeme.fr}".strip()


_ARTICLES = {
    "le": "m",
    "un": "m",
    "la": "f",
    "une": "f",
    "l'": "",
    "les": "",
    "des": "",
}


def _split_article(text: str) -> tuple[str | None, str]:
    match = re.match(r"^(le|la|les|un|une|des)\s+|^(l')", text)
    if not match:
        return None, text
    written = match.group(1) or match.group(2)
    return written, text[match.end() :]


def _no_reflexive(text: str) -> str:
    return re.sub(r"^(se |s')", "", text)


def check_recall(lexeme: Lexeme, answer: str) -> dict[str, Any]:
    """Compare a typed French answer with the word. Nouns need their article (or un/une) so
    the gender is practised; accents-only differences are reported separately."""
    expected = display(lexeme)
    typed = normalize(re.sub(r"[.!?,;:«»\"]", " ", answer))
    target = normalize(lexeme.fr)
    result: CheckResult = "incorrect"
    message = ""
    if lexeme.pos == "noun":
        written, word = _split_article(typed)
        same = word == target
        close = strip_accents(word) == strip_accents(target)
        if same or close:
            implied = _ARTICLES.get(written or "", "")
            if written is None:
                result, message = "article", f"Remember the article: {expected}."
            elif implied and lexeme.gender in ("m", "f") and implied != lexeme.gender:
                kind = "masculine" if lexeme.gender == "m" else "feminine"
                result, message = "gender", f"{lexeme.fr} is {kind}: {expected}."
            else:
                result = "correct" if same else "accent"
    else:
        bare_target, bare_typed = _no_reflexive(target), _no_reflexive(typed)
        if typed == target:
            result = "correct"
        elif strip_accents(typed) == strip_accents(target):
            result = "accent"
        elif lexeme.pos == "verb" and bare_target != target and bare_typed == bare_target:
            result, message = "article", f"Remember the reflexive pronoun: {expected}."
    if result == "accent":
        message = f"Almost: check the accents ({expected})."
    return {
        "result": result,
        "correct": result == "correct",
        "expected": expected,
        "message": message,
        "suggested_rating": SUGGESTED[result],
    }


# --- cards -----------------------------------------------------------------------------------


def lexeme_view(lexeme: Lexeme) -> dict[str, Any]:
    return {
        "id": lexeme.pk,
        "fr": lexeme.fr,
        "display": display(lexeme),
        "article": article(lexeme),
        "en": lexeme.en,
        "pos": lexeme.pos,
        "gender": lexeme.gender or None,
        "plural": lexeme.plural or None,
        "region": lexeme.region,
        "formality": lexeme.formality,
        "example_fr": lexeme.example_fr or None,
        "example_en": lexeme.example_en or None,
        "note": lexeme.note or None,
        "set": lexeme.vocab_set_id,
    }


def _fsrs_card(card: VocabCard) -> Card:
    return Card.from_dict(card.fsrs) if card.fsrs else Card(due=card.due)


def previews(card: VocabCard, now: datetime) -> dict[int, int]:
    """Seconds until the next review for each rating (no fuzz, so the labels are stable)."""
    state = _fsrs_card(card)
    out = {}
    for rating in Rating:
        scheduled, _ = PREVIEW.review_card(state, rating, review_datetime=now)
        out[int(rating)] = max(0, int((scheduled.due - now).total_seconds()))
    return out


def card_view(card: VocabCard, now: datetime) -> dict[str, Any]:
    return {
        "id": card.pk,
        "direction": card.direction,
        "is_new": card.reps == 0,
        "due": card.due.isoformat(),
        "lexeme": lexeme_view(card.lexeme),
        "previews": previews(card, now),
    }


def _start_of_day(now: datetime) -> datetime:
    return timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)


def _active(user: User) -> Any:
    return VocabCard.objects.filter(user=user, suspended=False, lexeme__retired=False)


def new_remaining(user: User, now: datetime) -> int:
    introduced = VocabReview.objects.filter(
        card__user=user, was_new=True, reviewed_at__gte=_start_of_day(now)
    ).count()
    return max(0, LearnerProfile.for_user(user).daily_new_cards - introduced)


def queue(user: User, *, limit: int = 20, learn_ahead: bool = False) -> dict[str, Any]:
    now = timezone.now()
    horizon = now + LEARN_AHEAD if learn_ahead else now
    cards = _active(user).select_related("lexeme")
    due = list(cards.filter(reps__gt=0, due__lte=horizon).order_by("due")[:limit])
    remaining = new_remaining(user, now)
    fresh: list[VocabCard] = []
    if len(due) < limit and remaining:
        unseen_recognition = VocabCard.objects.filter(
            user=user,
            lexeme=OuterRef("lexeme"),
            direction=VocabCard.Direction.RECOGNIZE,
            reps=0,
        )
        fresh = list(
            cards.filter(reps=0)
            .exclude(Q(direction=VocabCard.Direction.RECALL) & Exists(unseen_recognition))
            .order_by("lexeme__vocab_set__order", "lexeme__order", "-direction")[
                : min(limit - len(due), remaining)
            ]
        )
    upcoming = cards.filter(reps__gt=0, due__gt=horizon).order_by("due").first()
    return {
        "cards": [card_view(c, now) for c in due + fresh],
        "due_count": cards.filter(reps__gt=0, due__lte=now).count(),
        "new_remaining_today": remaining,
        "next_due": upcoming.due.isoformat() if upcoming else None,
    }


@transaction.atomic
def review(
    user: User,
    card_id: int,
    rating: int,
    *,
    duration_ms: int | None = None,
    answer: str = "",
    check_result: str = "",
) -> dict[str, Any]:
    card = VocabCard.objects.select_for_update().get(pk=card_id, user=user)
    now = timezone.now()
    state = _fsrs_card(card)
    was_review = state.state.name == "Review"
    scheduled, _log = SCHEDULER.review_card(
        state, Rating(rating), review_datetime=now, review_duration=duration_ms
    )
    VocabReview.objects.create(
        card=card,
        rating=rating,
        reviewed_at=now,
        duration_ms=duration_ms,
        answer=answer[:200],
        check_result=check_result[:12],
        was_new=card.reps == 0,
        due_before=card.due,
    )
    card.fsrs = scheduled.to_dict()
    card.due = scheduled.due
    card.reps += 1
    card.lapses += int(was_review and rating == Rating.Again)
    card.last_review = now
    card.save()
    return {
        "id": card.pk,
        "due": card.due.isoformat(),
        "interval_seconds": int((card.due - now).total_seconds()),
    }


def _word_key(fr: str, pos: str) -> tuple[str, str]:
    return normalize(fr), pos


def _deck_keys(cards: Any) -> set[tuple[str, str]]:
    return {_word_key(fr, pos) for fr, pos in cards.values_list("lexeme__fr", "lexeme__pos")}


def _put_in_deck(user: User, lexeme: Lexeme, now: datetime, *, has_cards: bool) -> None:
    """Resume a removed word's cards, or create both directions for a new one."""
    if has_cards:
        VocabCard.objects.filter(user=user, lexeme=lexeme).update(suspended=False)
        return
    for direction in VocabCard.Direction.values:
        VocabCard.objects.create(
            user=user,
            lexeme=lexeme,
            direction=direction,
            fsrs=Card(due=now).to_dict(),
            due=now,
        )


@transaction.atomic
def learn_set(user: User, vocab_set: VocabSet) -> dict[str, int]:
    """Add a set's words to the learner's deck (both directions). Words already in the deck
    from another set (same French word and part of speech) are skipped. Words removed earlier
    come back with their review history."""
    now = timezone.now()
    known = _deck_keys(VocabCard.objects.filter(user=user, suspended=False))
    removed = set(
        VocabCard.objects.filter(
            user=user, lexeme__vocab_set=vocab_set, suspended=True
        ).values_list("lexeme_id", flat=True)
    )
    added = skipped = 0
    for lexeme in vocab_set.lexemes.filter(retired=False):
        key = _word_key(lexeme.fr, lexeme.pos)
        if key in known:
            skipped += 1
            continue
        known.add(key)
        added += 1
        _put_in_deck(user, lexeme, now, has_cards=lexeme.pk in removed)
    return {"added": added, "skipped": skipped}


@transaction.atomic
def add_word(user: User, lexeme: Lexeme) -> dict[str, Any]:
    """Add one word to the learner's deck, unless it is already there (from any set)."""
    known = _deck_keys(VocabCard.objects.filter(user=user, suspended=False))
    if _word_key(lexeme.fr, lexeme.pos) in known:
        return {"lexeme": lexeme.pk, "added": False}
    has_cards = VocabCard.objects.filter(user=user, lexeme=lexeme).exists()
    _put_in_deck(user, lexeme, timezone.now(), has_cards=has_cards)
    return {"lexeme": lexeme.pk, "added": True}


def remove_set(user: User, vocab_set: VocabSet) -> dict[str, int]:
    """Take a set's words out of the learner's reviews. The cards are suspended, not deleted,
    so adding the set again resumes their schedule."""
    cards = VocabCard.objects.filter(user=user, lexeme__vocab_set=vocab_set, suspended=False)
    removed = cards.values("lexeme").distinct().count()
    cards.update(suspended=True)
    return {"removed": removed}


def remove_word(user: User, lexeme_id: int, *, removed: bool = True) -> dict[str, Any]:
    """Take a word out of the learner's reviews (both directions), or bring it back. Like
    remove_set, the cards are suspended so their schedule survives."""
    VocabCard.objects.filter(user=user, lexeme=lexeme_id).update(suspended=removed)
    return {"lexeme": lexeme_id, "removed": removed}


def set_summaries(user: User) -> list[dict[str, Any]]:
    now = timezone.now()
    sets = (
        VocabSet.objects.annotate(size=Count("lexemes", filter=Q(lexemes__retired=False)))
        .filter(size__gt=0)
        .order_by("order", "slug")  # Meta.ordering is ignored in aggregate queries
    )
    cards = (
        _active(user)
        .values("lexeme__vocab_set")
        .annotate(
            carded=Count("lexeme", distinct=True),
            due=Count("id", filter=Q(reps__gt=0, due__lte=now)),
            seen=Count("lexeme", filter=Q(reps__gt=0), distinct=True),
        )
    )
    by_set = {row["lexeme__vocab_set"]: row for row in cards}
    return [
        {
            "slug": s.slug,
            "kind": s.kind,
            "level": s.level,
            "title": s.title,
            "title_en": s.title_en,
            "lesson": s.lesson_id,
            "size": s.size,
            "in_deck": by_set.get(s.slug, {}).get("carded", 0),
            "seen": by_set.get(s.slug, {}).get("seen", 0),
            "due": by_set.get(s.slug, {}).get("due", 0),
        }
        for s in sets
    ]


def set_detail(user: User, vocab_set: VocabSet) -> dict[str, Any]:
    now = timezone.now()
    active = VocabCard.objects.filter(user=user, suspended=False)
    cards: dict[int, list[VocabCard]] = {}
    for card in active.filter(lexeme__vocab_set=vocab_set):
        cards.setdefault(card.lexeme_id, []).append(card)
    elsewhere = _deck_keys(active.exclude(lexeme__vocab_set=vocab_set))
    words = []
    for lexeme in vocab_set.lexemes.filter(retired=False):
        own = cards.get(lexeme.pk, [])
        status = (
            "elsewhere"
            if not own and _word_key(lexeme.fr, lexeme.pos) in elsewhere
            else "not_started"
            if not own
            else "new"
            if all(c.reps == 0 for c in own)
            else "due"
            if any(c.reps and c.due <= now for c in own)
            else "learning"
        )
        words.append({**lexeme_view(lexeme), "status": status})
    return {
        "slug": vocab_set.slug,
        "kind": vocab_set.kind,
        "level": vocab_set.level,
        "title": vocab_set.title,
        "title_en": vocab_set.title_en,
        "lesson": vocab_set.lesson_id,
        "words": words,
    }


def stats(user: User) -> dict[str, Any]:
    now = timezone.now()
    cards = _active(user)
    reviews_today = VocabReview.objects.filter(card__user=user, reviewed_at__gte=_start_of_day(now))
    new_waiting = cards.filter(reps=0).count()
    remaining = new_remaining(user, now)
    return {
        "cards": cards.count(),
        "words": cards.values("lexeme").distinct().count(),
        "due_now": cards.filter(reps__gt=0, due__lte=now).count(),
        "due_today": cards.filter(
            reps__gt=0, due__lt=_start_of_day(now) + timedelta(days=1)
        ).count(),
        "new_waiting": new_waiting,
        "new_remaining_today": remaining,
        # new cards a review session can actually show today: the daily allowance, capped by
        # the unseen cards in the deck
        "new_today": min(remaining, new_waiting),
        "reviews_today": reviews_today.count(),
        "mature": sum(
            1 for c in cards.filter(reps__gt=0).only("fsrs") if (c.fsrs.get("stability") or 0) >= 21
        ),
    }
