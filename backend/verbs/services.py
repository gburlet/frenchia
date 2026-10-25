"""Verb Station: catalogue, conjugation tables, drill building and deterministic grading.

Everything here is computed from the conjugation reference and the reviewed sentence banks
(content/verbs/); the LLM is never asked whether a form is correct."""

import random
import re
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.utils import timezone

from accounts.models import User
from contentkit.banks import Banks
from contentkit.conjugation import (
    PERSONS,
    SUBJECT_LABELS,
    TENSE_BY_KEY,
    TENSES,
    bare_infinitive,
    conjugation_table,
    forms_for,
    grade_conjugation,
    strip_accents,
    verb_slug,
)
from contentkit.models import VerbBank, VerbSentence
from contentkit.reference import Reference
from curriculum import content

from .models import ConjugationAttempt, VerbMastery

EWMA_WEIGHT = 0.3
SCORES = {"correct": 1.0, "accent": 0.5, "incorrect": 0.0}
MAX_DRILL = 40


class DrillError(Exception):
    pass


@dataclass
class Catalog:
    ref: Reference
    banks: Banks

    @property
    def hidden(self) -> set[str]:
        return set(self.banks.verb_sets.hidden) if self.banks.verb_sets else set()

    @property
    def sets(self) -> list[Any]:
        return list(self.banks.verb_sets.sets) if self.banks.verb_sets else []

    def verbs(self) -> list[str]:
        return sorted((v for v in self.ref.verbs if v not in self.hidden), key=_sort_key)

    def by_slug(self, slug: str) -> str | None:
        for infinitive in self.ref.verbs:
            if verb_slug(infinitive) == slug and infinitive not in self.hidden:
                return infinitive
        return None

    def bank(self, infinitive: str) -> VerbBank | None:
        entry = self.banks.verb_banks.get(verb_slug(infinitive))
        return entry[1] if entry else None


def catalog() -> Catalog:
    return Catalog(content.reference(), content.banks())


def _sort_key(infinitive: str) -> str:
    return strip_accents(bare_infinitive(infinitive))


def tense_list() -> list[dict[str, Any]]:
    return [
        {
            "key": t.key,
            "label": t.label,
            "label_en": t.label_en,
            "level": t.level,
            "mood": t.mood,
            "compound": t.compound,
            "drill": t.drill,
        }
        for t in TENSES
    ]


def verb_summary(cat: Catalog, infinitive: str) -> dict[str, Any]:
    verb = cat.ref.verbs[infinitive]
    bank = cat.bank(infinitive)
    return {
        "infinitive": infinitive,
        "slug": verb_slug(infinitive),
        "en": bank.en if bank else None,
        "group": verb["group"],
        "auxiliary": verb["auxiliary"],
        "pronominal": verb["pronominal"],
        "sentences": len(bank.sentences) if bank else 0,
        "sets": [s.id for s in cat.sets if infinitive in s.verbs],
    }


def verb_detail(cat: Catalog, infinitive: str, user: User) -> dict[str, Any]:
    verb = cat.ref.verbs[infinitive]
    bank = cat.bank(infinitive)
    mastery = VerbMastery.objects.filter(user=user, infinitive=infinitive)
    return {
        **verb_summary(cat, infinitive),
        "note": bank.note if bank else None,
        "participle_past": verb["participle_past"],
        "participle_present": verb["participle_present"],
        "table": conjugation_table(cat.ref, infinitive),
        "examples": [
            {
                "tense": s.tense,
                "tense_label": TENSE_BY_KEY[s.tense].label,
                "person": s.person,
                "fr": s.fr,
                "en": s.en,
                "form": s.form,
                "region": s.region,
            }
            for s in (bank.sentences if bank else [])
        ],
        "mastery": [
            {"tense": m.tense, "attempts": m.attempts, "ewma": round(m.ewma, 3)} for m in mastery
        ],
    }


# --- drills ---------------------------------------------------------------------------------


def _persons(tense: str, allowed: list[str] | None) -> list[str]:
    persons: list[str] = ["tu", "nous", "vous"] if tense.startswith("imperatif") else [*PERSONS]
    return [p for p in persons if not allowed or p in allowed] or persons


def _context_view(bank: VerbBank, index: int) -> dict[str, Any]:
    sentence = bank.sentences[index]
    match = re.search(re.escape(sentence.form), sentence.fr, re.IGNORECASE)
    start, end = match.span() if match else (len(sentence.fr), len(sentence.fr))
    return {
        "bank": bank.id,
        "version": bank.content_version,
        "index": index,
        "before": sentence.fr[:start],
        "after": sentence.fr[end:],
        "en": sentence.en,
        "region": sentence.region,
    }


def build_drill(
    user: User,
    *,
    verbs: list[str],
    tenses: list[str],
    persons: list[str] | None = None,
    mode: str = "mixed",
    count: int = 10,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Pick `count` items, favouring (verb, tense) pairs the learner gets wrong or hasn't seen."""
    rng = rng or random.Random()
    cat = catalog()
    verbs = [v for v in dict.fromkeys(verbs) if v in cat.ref.verbs and v not in cat.hidden]
    tenses = [t for t in dict.fromkeys(tenses) if t in TENSE_BY_KEY and TENSE_BY_KEY[t].drill]
    if not verbs or not tenses:
        raise DrillError("choose at least one verb and one tense")
    count = max(1, min(count, MAX_DRILL))
    mastery = {
        (m.infinitive, m.tense): m.ewma
        for m in VerbMastery.objects.filter(user=user, infinitive__in=verbs, tense__in=tenses)
    }
    sentences: dict[tuple[str, str], list[tuple[VerbBank, int]]] = {}
    for verb in verbs:
        bank = cat.bank(verb)
        if bank is None:
            continue
        for i, s in enumerate(bank.sentences):
            if s.tense in tenses and (not persons or s.person in persons):
                sentences.setdefault((verb, s.tense), []).append((bank, i))

    pairs = [(v, t) for v in verbs for t in tenses if forms_for(cat.ref, v, t)]
    if mode == "context":
        pairs = [p for p in pairs if p in sentences]
        if not pairs:
            raise DrillError("no context sentences for these verbs and tenses yet")
    weights = [1.2 if p not in mastery else 0.3 + 1.7 * (1 - mastery[p]) for p in pairs]
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for _ in range(count * 6):
        if len(items) >= count:
            break
        verb, tense = rng.choices(pairs, weights)[0]
        use_context = (verb, tense) in sentences and (
            mode == "context" or (mode == "mixed" and rng.random() < 0.6)
        )
        view = None
        person: str
        if use_context:
            bank, index = rng.choice(sentences[(verb, tense)])
            person = bank.sentences[index].person
            view = _context_view(bank, index)
        else:
            person = rng.choice(_persons(tense, persons))
        key = (verb, tense, person)
        if key in seen and len(seen) < len(pairs) * 6:
            continue
        seen.add(key)
        items.append(_item(cat, verb, tense, person, view))
    return items


def _item(
    cat: Catalog, verb: str, tense: str, person: str, sentence: dict[str, Any] | None
) -> dict[str, Any]:
    bank = cat.bank(verb)
    meta = TENSE_BY_KEY[tense]
    return {
        "infinitive": verb,
        "slug": verb_slug(verb),
        "en": bank.en if bank else None,
        "tense": tense,
        "tense_label": meta.label,
        "person": person,
        "subject": "" if tense.startswith("imperatif") else SUBJECT_LABELS[person],
        "mode": "context" if sentence else "form",
        "sentence": sentence,
    }


# --- answers --------------------------------------------------------------------------------


def _sentence(cat: Catalog, ref: dict[str, Any]) -> tuple[VerbBank, VerbSentence]:
    entry = cat.banks.verb_banks.get(str(ref.get("bank", "")))
    if entry is None:
        raise DrillError("unknown sentence bank")
    bank = entry[1]
    index = ref.get("index")
    if not isinstance(index, int) or not 0 <= index < len(bank.sentences):
        raise DrillError("unknown sentence")
    if ref.get("version") not in (None, bank.content_version):
        raise DrillError("this sentence has been updated; start a new drill")
    return bank, bank.sentences[index]


@transaction.atomic
def check_answer(
    user: User,
    *,
    infinitive: str,
    tense: str,
    person: str,
    answer: str,
    mode: str = "form",
    sentence: dict[str, Any] | None = None,
    time_spent_ms: int | None = None,
) -> dict[str, Any]:
    cat = catalog()
    if infinitive not in cat.ref.verbs or infinitive in cat.hidden:
        raise DrillError(f"unknown verb {infinitive!r}")
    if tense not in TENSE_BY_KEY or person not in _persons(tense, None):
        raise DrillError("unknown tense or person")
    expected_form = None
    snapshot = None
    if sentence is not None:
        bank, s = _sentence(cat, sentence)
        if (s.tense, s.person) != (tense, person) or bank.infinitive != infinitive:
            raise DrillError("the sentence does not match this item")
        expected_form = s.form
        snapshot = {"bank": bank.id, "version": bank.content_version, "fr": s.fr, "en": s.en}
        mode = ConjugationAttempt.Mode.CONTEXT
    grade = grade_conjugation(
        cat.ref, infinitive, tense, person, answer, expected_form=expected_form
    )
    ConjugationAttempt.objects.create(
        user=user,
        infinitive=infinitive,
        tense=tense,
        person=person,
        mode=mode if mode in ConjugationAttempt.Mode.values else ConjugationAttempt.Mode.FORM,
        sentence=snapshot,
        answer=answer[:200],
        expected=grade.expected[:200],
        result=grade.result,
        diagnosis=grade.diagnosis,
        time_spent_ms=time_spent_ms,
    )
    _update_mastery(user, infinitive, tense, SCORES[grade.result])
    said = snapshot["fr"] if snapshot else grade.expected
    return {
        "result": grade.result,
        "correct": grade.result == "correct",
        "expected": grade.expected,
        "accepted": grade.accepted,
        "diagnosis": grade.diagnosis,
        "message": grade.message,
        "said": said,
    }


def _update_mastery(user: User, infinitive: str, tense: str, score: float) -> None:
    mastery, _ = VerbMastery.objects.select_for_update().get_or_create(
        user=user, infinitive=infinitive, tense=tense
    )
    mastery.ewma = (
        score if mastery.attempts == 0 else (1 - EWMA_WEIGHT) * mastery.ewma + EWMA_WEIGHT * score
    )
    mastery.attempts += 1
    mastery.correct += score == 1.0
    mastery.last_practiced = timezone.now()
    mastery.save()


def progress(user: User) -> dict[str, Any]:
    rows = VerbMastery.objects.filter(user=user)
    weak = rows.filter(attempts__gte=2, ewma__lt=0.7).order_by("ewma", "-last_practiced")[:12]
    attempts = ConjugationAttempt.objects.filter(user=user)
    return {
        "attempts": attempts.count(),
        "correct": attempts.filter(result="correct").count(),
        "verbs_practiced": rows.values("infinitive").distinct().count(),
        "weak_spots": [
            {
                "infinitive": m.infinitive,
                "slug": verb_slug(m.infinitive),
                "tense": m.tense,
                "tense_label": TENSE_BY_KEY[m.tense].label if m.tense in TENSE_BY_KEY else m.tense,
                "attempts": m.attempts,
                "ewma": round(m.ewma, 3),
            }
            for m in weak
        ],
    }
