"""Generation job lifecycle: create -> run (worker) -> needs review -> approve/reject/revise."""

import logging
import traceback
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from contentkit.models import Lesson as LessonContent
from contentkit.models import LessonOutline, Level
from contentkit.reference import Reference
from contentkit.yamlio import load_yaml
from curriculum.importer import import_content
from curriculum.models import GrammarTopic, Lesson
from inference.errors import InferenceTimeout, InferenceUnavailable
from inference.llm import ChatModel
from inference.providers import get_authoring_chat_model

from .generation import GenerationResult, LessonBrief, LessonGenerator, LessonReviser
from .models import GenerationJob
from .writer import ContentWriter, WriteConflict

logger = logging.getLogger(__name__)

MAX_ROUNDS = 4  # generations of one draft before auto-review hands it to a human
RETRY_NOTE = "LLM unavailable"
RETRY_DELAY = timedelta(minutes=5)
MAX_RETRIES = 6


class ReviewError(Exception):
    pass


def _root() -> Path:
    return Path(settings.CONTENT_DIR)


def _next_version(lesson: Lesson, writer: ContentWriter) -> int:
    imported = lesson.revisions.aggregate(v=Max("content_version"))["v"] or 0
    current = writer.read_lesson(
        writer.root / "lessons" / lesson.level.lower() / f"{lesson.slug}.yaml"
    )
    return max(imported, current.content_version if current else 0) + 1


def create_job(
    lesson: Lesson,
    *,
    kind: str = GenerationJob.Kind.LESSON,
    notes: str = "",
    targets: list[str] | None = None,
    parent: GenerationJob | None = None,
    enqueue: bool = True,
) -> GenerationJob:
    writer = ContentWriter(_root())
    with transaction.atomic():
        job = GenerationJob.objects.create(
            kind=kind,
            lesson=lesson,
            notes=notes,
            targets=targets or [],
            parent=parent,
            # A revision of a draft builds on what was published when that draft began; once the
            # parent itself is published, the file holds its output, so start from that.
            base_hash=parent.base_hash
            if parent and parent.status != GenerationJob.Status.APPROVED
            else writer.current_hash(lesson.slug, lesson.level),
        )
        if parent is not None and parent.status == GenerationJob.Status.NEEDS_REVIEW:
            parent.status = GenerationJob.Status.REJECTED
            parent.reviewer_notes = f"Superseded by revision job {job.pk}: {notes}"
            parent.reviewed_at = timezone.now()
            parent.save(update_fields=["status", "reviewer_notes", "reviewed_at"])
        if enqueue:
            transaction.on_commit(lambda: _enqueue(job))
    return job


def brief_for(lesson: Lesson) -> LessonBrief:
    outline = LessonOutline.model_validate(lesson.outline)
    topics = GrammarTopic.objects.filter(slug__in=outline.grammar_topics)
    prereqs = Lesson.objects.filter(slug__in=outline.prerequisites)
    return LessonBrief(
        outline=outline,
        level=cast(Level, lesson.level),  # curriculum.Level choices == contentkit Level
        unit_id=lesson.unit_id,
        unit_title=lesson.unit.title,
        topic_titles=[t.title for t in topics],
        prerequisite_titles=[p.title for p in prereqs],
    )


def run_job(job_id: int) -> GenerationJob:
    job = GenerationJob.objects.select_related("lesson__unit", "parent").get(pk=job_id)
    if job.status != GenerationJob.Status.QUEUED:
        return job
    writer = ContentWriter(_root())
    chat = get_authoring_chat_model()
    job.status, job.started_at, job.model = GenerationJob.Status.RUNNING, timezone.now(), chat.model
    job.save(update_fields=["status", "started_at", "model"])

    def progress(message: str) -> None:
        job.progress = [
            *job.progress,
            {"at": timezone.now().isoformat(timespec="seconds"), "message": message},
        ]
        GenerationJob.objects.filter(pk=job.pk).update(progress=job.progress)

    try:
        ref = Reference.load(_root())
        result = _generate(job, chat, ref, writer, progress)
        draft_path = writer.write_draft(result.lesson, job.pk)
        job.output = result.lesson.model_dump(mode="json", exclude_none=True)
        job.draft_path = str(draft_path.relative_to(writer.root))
        job.validation = [
            {"severity": i.severity, "path": i.path, "message": i.message} for i in result.issues
        ]
        job.prompts = result.prompts
        job.llm_calls, job.llm_seconds = result.stats.calls, round(result.stats.seconds, 1)
        job.completion_tokens = result.stats.tokens
        job.status = GenerationJob.Status.NEEDS_REVIEW
    except (InferenceUnavailable, InferenceTimeout) as exc:
        # The LLM is down or overloaded (e.g. the Mac ran out of memory): wait and start again
        # instead of failing a whole queue of jobs in seconds.
        retries = sum(p["message"].startswith(RETRY_NOTE) for p in job.progress)
        if retries < MAX_RETRIES:
            progress(f"{RETRY_NOTE} ({exc}); retrying in {RETRY_DELAY.seconds // 60} min")
            job.status, job.started_at = GenerationJob.Status.QUEUED, None
            job.save(update_fields=["status", "started_at"])
            _enqueue(job, run_after=timezone.now() + RETRY_DELAY)
            return job
        logger.exception("Generation job %s failed", job.pk)
        job.status = GenerationJob.Status.FAILED
        job.error = f"{exc}\n\n{traceback.format_exc()}"
    except Exception as exc:
        logger.exception("Generation job %s failed", job.pk)
        job.status = GenerationJob.Status.FAILED
        job.error = f"{exc}\n\n{traceback.format_exc()}"
    job.finished_at = timezone.now()
    # Rejected while it ran (e.g. superseded from Admin): keep the rejection, drop the draft.
    if GenerationJob.objects.filter(pk=job.pk, status=GenerationJob.Status.REJECTED).exists():
        _discard_draft(job, writer)
        GenerationJob.objects.filter(pk=job.pk).update(finished_at=job.finished_at)
        job.status = GenerationJob.Status.REJECTED
        return job
    job.save()
    if (
        job.status == GenerationJob.Status.NEEDS_REVIEW
        and not settings.AUTHORING["EXTERNAL_REVIEW"]
    ):
        auto_review(job, progress)
    return job


# Issues that come from the LLM (critic) or from generation itself, not from today's
# deterministic checks: revalidating keeps them.
_NOT_DETERMINISTIC = ("AI critic", "dropped", "kept unrevised")


def revalidate(job: GenerationJob) -> None:
    """Re-run today's deterministic checks on a draft: checks added since it was generated
    report their problems, and errors a fixed check no longer reports are dropped."""
    from contentkit.validate import check_lesson_quality

    if not job.output:
        return
    lesson = LessonContent.model_validate(job.output)
    # Errors block approval, so they are recomputed; warnings (and LLM findings) are kept.
    kept = [
        v
        for v in job.validation
        if v["severity"] != "error" or v["message"].startswith(_NOT_DETERMINISTIC)
    ]
    known = {(v["path"], v["message"]) for v in kept}
    fresh = [
        {"severity": i.severity, "path": i.path, "message": i.message}
        for i in check_lesson_quality(lesson, Reference.load(_root()))
        if (i.path, i.message) not in known
    ]
    validation = [*kept, *fresh]
    if validation != job.validation:
        job.validation = validation
        job.save(update_fields=["validation"])


def generation_round(job: GenerationJob) -> int:
    """How many generations led to this job (1 for a fresh draft)."""
    depth = 1
    while job.parent_id is not None:
        job, depth = job.parent, depth + 1  # type: ignore[assignment]
    return depth


def auto_review(job: GenerationJob, progress: Callable[[str], None] | None = None) -> None:
    """Review without an external proof-reader (a large remote author, ADR 0007): publish a
    draft that passes every deterministic check and that the AI critic did not flag; otherwise
    queue a revision with the problems as notes, and after MAX_ROUNDS leave it for a human."""
    from .external_review import critic_flags, needs_attention, validation_notes, warning_notes

    note = progress or (lambda message: None)
    attention, critic = needs_attention(job), critic_flags(job)
    if not job.error_count and not attention and not critic:
        try:
            note(f"Auto-review: published {approve(job).name}")
        except ReviewError as exc:
            note(f"Auto-review: not published: {exc}")
        return
    if generation_round(job) >= MAX_ROUNDS:
        try:  # the learner's rule: publish after the last round rather than wait in Admin
            path = approve(job, allow_errors=True)
            note(f"Auto-review: published after {MAX_ROUNDS} rounds: {path.name}")
        except ReviewError as exc:
            note(f"Auto-review: not published after {MAX_ROUNDS} rounds: {exc}")
        return
    parts = [validation_notes(job), warning_notes(attention), critic_notes(critic)]
    notes = "\n".join(n for n, _ in parts if n)
    child = request_revision(job, notes, sorted({t for _, ts in parts for t in ts}))
    note(f"Auto-review: revision job {child.pk} queued")


def critic_notes(flags: list[dict[str, str]]) -> tuple[str, list[str]]:
    notes = "\n".join(
        f"- {f['path'].split(':', 1)[-1]}: {f['message']} Fix it if it is a real error."
        for f in flags
    )
    targets = sorted({f["path"].split(":", 1)[1] for f in flags if ":" in f["path"]})
    return notes, targets


def _enqueue(job: GenerationJob, **options: Any) -> None:
    """A revision is short and finishes a lesson that is nearly done: run it before new drafts
    queued in bulk."""
    from .tasks import run_generation_job

    if job.kind == GenerationJob.Kind.REVISION:
        options.setdefault("priority", 100)
    run_generation_job.using(**options).enqueue(job.pk)


def _generate(
    job: GenerationJob,
    chat: ChatModel,
    ref: Reference,
    writer: ContentWriter,
    progress: Callable[[str], None],
) -> GenerationResult:
    lesson = job.lesson
    if job.kind == GenerationJob.Kind.LESSON:
        return LessonGenerator(chat, ref, progress).generate(
            brief_for(lesson), content_version=_next_version(lesson, writer), job_id=job.pk
        )
    if job.parent is not None and job.parent.output:
        base = dict(job.parent.output)
        version = (
            _next_version(lesson, writer)  # the parent went live: this is a new version
            if job.parent.status == GenerationJob.Status.APPROVED
            else int(base["content_version"])  # still an unpublished draft: same version
        )
    else:
        path = writer.root / "lessons" / lesson.level.lower() / f"{lesson.slug}.yaml"
        if not path.exists():
            raise ReviewError("nothing to revise: the lesson has no content yet")
        base, version = load_yaml(path), _next_version(lesson, writer)
    outline = brief_for(lesson).outline  # the outline may have changed since the draft
    base["objectives"] = list(outline.objectives)
    if not outline.quebec_focus:  # a Québec/France note the outline no longer calls for
        base["sections"] = [s for s in base["sections"] if s.get("type") != "regional_note"]
    return LessonReviser(chat, ref, progress).revise(
        base, job.notes, list(job.targets), content_version=version, job_id=job.pk
    )


def approve(
    job: GenerationJob, *, allow_errors: bool = False, allow_overwrite_edits: bool = False
) -> Path:
    if job.status != GenerationJob.Status.NEEDS_REVIEW or not job.output:
        raise ReviewError(f"job {job.pk} is not awaiting review")
    if job.error_count and not allow_errors:
        raise ReviewError(
            f"draft has {job.error_count} validation errors; fix or request a revision"
        )
    writer = ContentWriter(_root())
    draft = LessonContent.model_validate(job.output)
    if job.lesson.revisions.filter(content_version__gte=draft.content_version).exists():
        # Its version went live meanwhile (a revision of a draft that was then published).
        draft = draft.model_copy(update={"content_version": _next_version(job.lesson, writer)})
    target = writer.lesson_path(draft)
    previous = target.read_text(encoding="utf-8") if target.exists() else None
    # A revision of the current file already contains its manual edits.
    based_on_file = job.kind == GenerationJob.Kind.REVISION and job.parent is None
    try:
        writer.promote(
            draft,
            base_hash=job.base_hash,
            allow_overwrite_edits=allow_overwrite_edits or based_on_file,
        )
    except WriteConflict as exc:
        raise ReviewError(str(exc)) from exc
    result = import_content(_root(), only={draft.id}, publish=True)
    if result.refused:
        if previous is None:
            target.unlink(missing_ok=True)
        else:
            target.write_text(previous, encoding="utf-8")
        raise ReviewError("import refused: " + "; ".join(result.refused))
    _discard_draft(job, writer)
    job.status, job.reviewed_at = GenerationJob.Status.APPROVED, timezone.now()
    job.save(update_fields=["status", "reviewed_at", "draft_path"])
    return target


def reject(job: GenerationJob, notes: str = "") -> None:
    if job.status not in (GenerationJob.Status.NEEDS_REVIEW, GenerationJob.Status.FAILED):
        raise ReviewError(f"job {job.pk} cannot be rejected in status {job.status}")
    _discard_draft(job, ContentWriter(_root()))
    job.status, job.reviewer_notes, job.reviewed_at = (
        GenerationJob.Status.REJECTED,
        notes,
        timezone.now(),
    )
    job.save(update_fields=["status", "reviewer_notes", "reviewed_at", "draft_path"])


def request_revision(
    job: GenerationJob, notes: str, targets: list[str] | None = None
) -> GenerationJob:
    if job.status != GenerationJob.Status.NEEDS_REVIEW:
        raise ReviewError(f"job {job.pk} is not awaiting review")
    if not notes.strip():
        raise ReviewError("describe what should change")
    _discard_draft(job, ContentWriter(_root()))
    return create_job(
        job.lesson, kind=GenerationJob.Kind.REVISION, notes=notes, targets=targets, parent=job
    )


def _discard_draft(job: GenerationJob, writer: ContentWriter) -> None:
    if job.draft_path:
        (writer.root / job.draft_path).unlink(missing_ok=True)
        job.draft_path = ""
