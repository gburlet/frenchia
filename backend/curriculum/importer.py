"""Import content files into the database: idempotent, versioned, never destructive.

- Structure (units, grammar topics, lesson slots) is upserted from the outlines.
- Each lesson file becomes a LessonRevision keyed by (lesson, content_version):
  same version + same hash -> no-op; same version + different hash -> refused (bump the
  version); lower version than one already imported -> refused.
- Exercises get a new immutable ExerciseRevision per lesson revision.
- Nothing is published unless asked; publishing and rollback only move a pointer.
"""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from contentkit.models import Lesson as LessonContent
from contentkit.validate import Issue, Repository, validate_repository
from contentkit.yamlio import content_hash

from .models import (
    ContentImport,
    Exercise,
    ExerciseRevision,
    GrammarTopic,
    Lesson,
    LessonRevision,
    Unit,
)


@dataclass
class ImportResult:
    created: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    published: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)
    record: ContentImport | None = None

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    def summary(self) -> dict[str, list[str]]:
        return {k: getattr(self, k) for k in ("created", "unchanged", "published", "refused")}


class ImportAborted(Exception):
    pass


def import_content(
    root: Path,
    *,
    dry_run: bool = False,
    publish: bool = False,
    only: set[str] | None = None,
) -> ImportResult:
    repo = validate_repository(root)
    result = ImportResult(issues=list(repo.issues))
    structural = [i for i in repo.errors if not i.path.startswith(("lessons/", *repo.lessons))]
    record = ContentImport.objects.create(dry_run=dry_run, git_sha=_git_sha(root))
    result.record = record
    try:
        with transaction.atomic():
            if structural:
                raise ImportAborted("curriculum or grammar files have errors")
            _sync_structure(repo)
            bad = {i.path.split(":")[0] for i in repo.errors}
            for lesson_id, (path, lesson) in repo.lessons.items():
                if only and lesson_id not in only:
                    continue
                rel = str(path.relative_to(root))
                if rel in bad or lesson_id in bad:
                    result.refused.append(f"{lesson_id}: has validation errors")
                    continue
                _import_lesson(lesson, rel, record, result, publish=publish)
            imported_paths = {str(path.relative_to(root)) for path, _ in repo.lessons.values()}
            unparsable = {
                i.path.split(":")[0] for i in repo.errors if i.path.startswith("lessons/")
            }
            for rel in sorted(unparsable - imported_paths):
                result.refused.append(f"{rel}: invalid file")
            if dry_run:
                transaction.set_rollback(True)
        record.ok = not result.refused
    except ImportAborted as exc:
        result.refused.append(str(exc))
    record.summary = result.summary()
    record.issues = [
        {"severity": i.severity, "path": i.path, "message": i.message} for i in result.issues
    ]
    record.finished_at = timezone.now()
    record.save()
    return result


def _sync_structure(repo: Repository) -> None:
    if repo.topics:
        for topic in repo.topics.topics:
            GrammarTopic.objects.update_or_create(
                slug=topic.id,
                defaults={"level": topic.level, "title": topic.title, "related": topic.related},
            )
    order = 0
    for level in sorted(repo.levels.values(), key=lambda lvl: lvl.level):
        for unit_index, unit in enumerate(level.units):
            Unit.objects.update_or_create(
                slug=unit.id,
                defaults={
                    "level": level.level,
                    "order": _level_rank(level.level) * 100 + unit_index,
                    "title": unit.title,
                    "objectives": list(unit.objectives),
                },
            )
            for outline in unit.lessons:
                order += 1
                lesson, _ = Lesson.objects.update_or_create(
                    slug=outline.id,
                    defaults={
                        "unit_id": unit.id,
                        "order": order,
                        "kind": outline.kind,
                        "title": outline.title,
                        "outline": outline.model_dump(mode="json", exclude_none=True),
                    },
                )
                lesson.grammar_topics.set(
                    GrammarTopic.objects.filter(slug__in=outline.grammar_topics)
                )


def _import_lesson(
    content: LessonContent,
    source_path: str,
    record: ContentImport,
    result: ImportResult,
    *,
    publish: bool,
) -> None:
    digest = content_hash(content)
    lesson = Lesson.objects.get(slug=content.id)
    existing = lesson.revisions.filter(content_version=content.content_version).first()
    label = f"{content.id} v{content.content_version}"
    if existing is not None:
        if existing.content_hash == digest:
            result.unchanged.append(label)
        else:
            result.refused.append(
                f"{label}: content changed without bumping content_version "
                f"(already imported with a different hash)"
            )
        return
    latest = lesson.revisions.aggregate(v=Max("content_version"))["v"]
    if latest is not None and content.content_version < latest:
        result.refused.append(f"{label}: older than imported v{latest}")
        return
    revision = LessonRevision.objects.create(
        lesson=lesson,
        content_version=content.content_version,
        content_hash=digest,
        payload=content.model_dump(mode="json", exclude_none=True),
        source_path=source_path,
        is_manually_edited=bool(content.provenance and content.provenance.generated_hash != digest),
        content_import=record,
    )
    for exercise in content.exercises:
        stable_id = f"{content.id}/{exercise.id}"
        row, _ = Exercise.objects.update_or_create(
            stable_id=stable_id, defaults={"lesson": lesson, "kind": exercise.type}
        )
        ExerciseRevision.objects.create(
            exercise=row,
            lesson_revision=revision,
            content_hash=content_hash(exercise),
            payload=exercise.model_dump(mode="json", exclude_none=True),
        )
    result.created.append(label)
    if publish:
        publish_revision(revision)
        result.published.append(label)


def publish_revision(revision: LessonRevision) -> None:
    """Make `revision` the live version of its lesson (also used for rollback)."""
    if revision.published_at is None:
        revision.published_at = timezone.now()
        revision.save(update_fields=["published_at"])
    Lesson.objects.filter(pk=revision.lesson_id).update(published_revision=revision)


def _level_rank(level: str) -> int:
    return ["A1", "A2", "B1", "B2", "C1", "C2"].index(level)


def _git_sha(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5
        )
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""
