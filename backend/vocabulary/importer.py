"""Projection of vocabulary content into the database.

- Themed sets (content/vocabulary/sets/<id>.yaml) follow the lesson rules: same version and
  hash -> no-op; same version with a different hash -> refused (bump content_version); older
  version -> refused.
- Lesson sets are derived from each lesson's published revision (vocabulary sections and
  reading glossaries) and resynced whenever a revision is published or rolled back.
- Lexemes are updated in place so learners keep their scheduling; dropped words are retired,
  never deleted."""

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from contentkit.conjugation import verb_slug
from contentkit.models import VocabSet as VocabSetContent
from contentkit.validate import Repository
from contentkit.yamlio import content_hash
from curriculum.models import Lesson

from .models import Lexeme, VocabSet

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
LEXEME_FIELDS = (
    "fr",
    "en",
    "pos",
    "gender",
    "plural",
    "region",
    "formality",
    "example_fr",
    "example_en",
    "note",
)


def _digest(data: Any) -> str:
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def import_theme_sets(
    repo: Repository, *, created: list[str], unchanged: list[str], refused: list[str]
) -> None:
    if repo.banks is None:
        return
    bad = {i.path.split(":")[0] for i in repo.errors if i.path.startswith("vocabulary/")}
    themes = (
        {t.id: i for i, t in enumerate(repo.banks.vocab_themes.themes)}
        if repo.banks.vocab_themes
        else {}
    )
    for set_id, (path, content) in repo.banks.vocab_sets.items():
        rel = str(path.relative_to(repo.root))
        label = f"vocabulary:{set_id} v{content.content_version}"
        if rel in bad:
            refused.append(f"{label}: has validation errors")
            continue
        digest = content_hash(content)
        existing = VocabSet.objects.filter(slug=set_id).first()
        if existing is not None:
            if existing.content_version == content.content_version:
                if existing.content_hash == digest:
                    unchanged.append(label)
                else:
                    refused.append(f"{label}: content changed without bumping content_version")
                continue
            if content.content_version < existing.content_version:
                refused.append(f"{label}: older than imported v{existing.content_version}")
                continue
        vocab_set, _ = VocabSet.objects.update_or_create(
            slug=set_id,
            defaults={
                "kind": VocabSet.Kind.THEME,
                "level": content.level,
                "title": content.title,
                "title_en": content.title_en,
                "order": LEVEL_ORDER.get(content.level, 9) * 1000 + themes.get(set_id, 999),
                "content_version": content.content_version,
                "content_hash": digest,
                "source_path": rel,
            },
        )
        _sync_lexemes(vocab_set, _theme_entries(content))
        created.append(label)


def _theme_entries(content: VocabSetContent) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            f"{content.id}/{entry.id}",
            {field: getattr(entry, field) or "" for field in LEXEME_FIELDS},
        )
        for entry in content.entries
    ]


def _sync_lexemes(vocab_set: VocabSet, entries: Iterable[tuple[str, dict[str, Any]]]) -> None:
    keep: list[str] = []
    for order, (stable_id, fields) in enumerate(entries):
        keep.append(stable_id)
        Lexeme.objects.update_or_create(
            stable_id=stable_id,
            defaults={
                **fields,
                "vocab_set": vocab_set,
                "order": order,
                "content_hash": _digest(fields),
                "retired": False,
            },
        )
    vocab_set.lexemes.exclude(stable_id__in=keep).update(retired=True)


def lesson_vocabulary(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Vocabulary items of a lesson payload: vocabulary sections, then reading glossaries."""
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    sections = payload.get("sections", [])
    ordered = [s for s in sections if s["type"] == "vocabulary"] + [
        s for s in sections if s["type"] == "reading"
    ]
    for section in ordered:
        for item in section.get("items") or section.get("glossary") or []:
            key = item["fr"].casefold()
            if key not in seen:
                seen.add(key)
                items.append(item)
    return items


def sync_lesson_set(lesson: Lesson) -> VocabSet | None:
    """Make the lesson's vocabulary set match its published revision."""
    revision = lesson.published_revision
    slug = f"lesson-{lesson.slug}"
    if revision is None:
        VocabSet.objects.filter(slug=slug).update(content_hash="")
        Lexeme.objects.filter(vocab_set_id=slug).update(retired=True)
        return None
    items = lesson_vocabulary(revision.payload)
    if not items:
        Lexeme.objects.filter(vocab_set_id=slug).update(retired=True)
        return None
    payload = revision.payload
    vocab_set, _ = VocabSet.objects.update_or_create(
        slug=slug,
        defaults={
            "kind": VocabSet.Kind.LESSON,
            "level": payload["level"],
            "title": payload["title"],
            "title_en": payload["title_en"],
            "order": 100_000 + lesson.order,
            "lesson": lesson,
            "content_version": revision.content_version,
            "content_hash": revision.content_hash,
            "source_path": revision.source_path,
        },
    )
    entries = [
        (
            f"{slug}/{verb_slug(item['fr'])}",
            {field: item.get(field) or "" for field in LEXEME_FIELDS},
        )
        for item in items
    ]
    _sync_lexemes(vocab_set, entries)
    return vocab_set


def sync_lesson_sets() -> int:
    count = 0
    for lesson in Lesson.objects.select_related("published_revision"):
        if sync_lesson_set(lesson) is not None:
            count += 1
    return count
