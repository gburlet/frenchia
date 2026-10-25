"""External proof-reading of generated lessons by a stronger model (ADR 0003).

The reviewer runs outside the app, e.g. as a Claude Code Haiku subagent. Export writes one
self-contained prompt per job awaiting review, the reviewer writes findings JSON next to
it, and import attaches the findings to the job, where they appear in Admin as suggestions.
Nothing is applied automatically: findings can become revision notes for the local LLM."""

import json
from pathlib import Path
from typing import Literal

from django.utils import timezone
from pydantic import BaseModel, ConfigDict, ValidationError

from contentkit.reference import Reference
from contentkit.validate import UNVERIFIED_QUEBEC

from .models import GenerationJob

PROMPT_VERSION = "1"
REVIEW_DIR = Path("drafts") / "review"


class Finding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    severity: Literal["error", "suggestion"]
    category: Literal[
        "grammar",
        "spelling",
        "meaning",
        "translation",
        "exercise_design",
        "quebec_usage",
        "consistency",
        "other",
    ]
    problem: str
    suggested_fix: str


class Review(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[Finding]


PROMPT = """\
You are reviewing a lesson that a smaller model generated for an English-speaking adult learning \
Québec French (CEFR {level}). The learner will study it and be graded against its answer keys, so \
errors teach mistakes. Review it as an expert teacher and report every real problem:
- every French sentence: grammar, agreement, prepositions (parler à…), articles, accents, \
naturalness;
- translations in both directions;
- answer keys: each fill-in-the-blank must be fully correct once filled; each multiple-choice \
question must have exactly one correct option (an option that is the right answer with different \
punctuation is also correct);
- Québec usage: Québec usage is the default (déjeuner = breakfast, dîner = lunch, souper = supper; \
« la fin de semaine », not « le week-end »). Flag claims about Québec usage that are wrong or \
misplaced, but only when you are certain;
- consistency: notes must be about the sentence they're attached to; glossary words are written \
without articles; explanations must describe mistakes learners really make.
Use item_id = the id of the section or exercise. severity 'error' = must fix; 'suggestion' = could \
be better. Do not report style preferences as errors, and do not invent problems.

Verified Québec usage:
{lexicon}

Lesson (JSON):
{lesson}

Answer with a single JSON object matching this JSON Schema:
{schema}"""


def build_prompt(lesson: dict[str, object], ref: Reference) -> str:
    lexicon = "\n".join(f"- {t.term}: {t.meaning} (France: {t.france})" for t in ref.quebec)
    lesson_data = {k: v for k, v in lesson.items() if k != "provenance"}
    return PROMPT.format(
        level=lesson["level"],
        lexicon=lexicon or "(none)",
        lesson=json.dumps(lesson_data, ensure_ascii=False, indent=1),
        schema=json.dumps(Review.model_json_schema(), indent=1),
    )


def pending_jobs() -> list[GenerationJob]:
    return list(
        GenerationJob.objects.filter(
            status=GenerationJob.Status.NEEDS_REVIEW, external_reviewed_at__isnull=True
        ).order_by("pk")
    )


def export(content_root: Path, jobs: list[GenerationJob]) -> Path:
    out = content_root / REVIEW_DIR
    out.mkdir(parents=True, exist_ok=True)
    ref = Reference.load(content_root)
    for job in jobs:
        assert job.output is not None
        (out / f"job-{job.pk}.prompt.txt").write_text(
            build_prompt(job.output, ref), encoding="utf-8"
        )
    return out


def import_findings(content_root: Path, reviewer: str) -> tuple[list[int], list[str]]:
    """Attach every job-<id>.findings.json in the review directory. Returns (job ids, errors)."""
    folder = content_root / REVIEW_DIR
    imported: list[int] = []
    errors: list[str] = []
    for path in sorted(folder.glob("job-*.findings.json")):
        job_id = int(path.name.split(".")[0].removeprefix("job-"))
        job = GenerationJob.objects.filter(pk=job_id).first()
        if job is None or job.status != GenerationJob.Status.NEEDS_REVIEW:
            errors.append(f"{path.name}: job {job_id} is not awaiting review")
            continue
        try:
            review = Review.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc.errors()[0]['msg']}")
            continue
        known = {
            item["id"] for key in ("sections", "exercises") for item in (job.output or {})[key]
        }
        job.external_review = [
            {**f.model_dump(), "unknown_item": f.item_id not in known} for f in review.issues
        ]
        job.external_reviewer = f"{reviewer} (prompt v{PROMPT_VERSION})"
        job.external_reviewed_at = timezone.now()
        job.save(update_fields=["external_review", "external_reviewer", "external_reviewed_at"])
        for leftover in (path, folder / f"job-{job_id}.prompt.txt"):
            leftover.unlink(missing_ok=True)
        imported.append(job_id)
    return imported, errors


def revision_notes(
    job: GenerationJob, *, include_suggestions: bool = True
) -> tuple[str, list[str]]:
    """Turn findings into revision notes and target ids for the local LLM."""
    findings = [f for f in job.external_review if include_suggestions or f["severity"] == "error"]
    notes = "\n".join(
        f"- {f['item_id']} ({f['severity']}): {f['problem']} Fix: {f['suggested_fix']}"
        for f in findings
    )
    targets = sorted({f["item_id"] for f in findings if not f.get("unknown_item")})
    return notes, targets


def needs_attention(job: GenerationJob) -> list[dict[str, str]]:
    """Warnings that must not be published without a revision or a human: Québec claims
    missing from the verified lexicon and sentences the AI critic flagged. Haiku misses these
    (it passed « avoir le feu au cul » as a Québec expression)."""
    return [
        v
        for v in job.validation
        if UNVERIFIED_QUEBEC in v["message"] or v["message"].startswith("AI critic")
    ]


def warning_notes(warnings: list[dict[str, str]]) -> tuple[str, list[str]]:
    notes = "\n".join(
        f"- {w['path'].split(':', 1)[-1]}: {w['message']} Fix: use only verified Québec usage "
        "(otherwise standard French, region common), and correct or replace the sentence."
        for w in warnings
    )
    targets = sorted({w["path"].split(":", 1)[-1] for w in warnings if ":" in w["path"]})
    return notes, targets
