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
from curriculum.models import Lesson

from .models import GenerationJob

PROMPT_VERSION = "9"
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
You are reviewing a lesson that a language model generated for an English-speaking adult learning \
Québec French (CEFR {level}). The learner will study it and be graded against its answer keys, so \
errors teach mistakes. Review it as an expert teacher and report every real problem:
- every French sentence: grammar, agreement, prepositions (parler à…), articles, accents, \
naturalness;
- translations in both directions;
- answer keys: each fill-in-the-blank must be fully correct once filled, and must not have \
another equally correct answer that is not listed (e.g. any pronoun fits « Je ___ dis la \
vérité »). A blank lists at most 4 answers: when more than 4 fit (synonymous connectors), \
report that the sentence or hint is too open, not a list of answers to add; each \
multiple-choice question must have exactly one correct option (work it out \
yourself before reading answer_index; an option that is the right answer with different \
punctuation is also correct); an answer must not repeat an object already replaced by a \
pronoun (« Je lui parle à Marie »); a fill-in-the-blank hint must not contain the answer. \
These grade the learner unfairly, so they are errors. Translations are different: a model \
grades answers that are not listed, so a missing alternative translation is not an error, and \
a translation hint may give vocabulary;
- expressions must be real and in standard register: an invented idiom or a vulgar one is an \
error;
- Québec usage: Québec usage is the default (déjeuner = breakfast, dîner = lunch, souper = supper; \
« la fin de semaine », not « le week-end »; courriel; in Québec « bon matin » and \
« bon après-midi » greet as well as take leave, and « allô » is an informal hello). France \
forms where Québec has a default (petit-déjeuner, le week-end, mail, portable for a phone) \
should be adapted. Flag claims about Québec usage that are wrong or misplaced, but only \
when you are certain;
- explanations, tables, examples, regional notes, readings and glossaries are taught as fact: \
a wrong rule, a wrong form in a table, a wrong translation (Québec dîner = lunch: « dinner » \
for dîner is wrong; souper may be translated « supper » or « dinner ») or a wrong date is an \
error, like a wrong answer key;
- Québec forms are used where a word naturally comes up; do not ask for more Québec-specific \
vocabulary. Report as an error any sentence, setting or vocabulary item that brings in a \
Québec-specific word for its own sake (a dépanneur, souper, cabane à sucre or poutine in a \
lesson whose topic doesn't call for it; « practise with Québec words » advice), and \
vocabulary that is too narrow (the same few words reused) or not suited to the CEFR level;
- consistency: notes must be about the sentence they're attached to; glossary words are written \
without articles; explanations must describe mistakes learners really make.
Use item_id = the id of the section or exercise. severity 'error' = must fix; 'suggestion' = could \
be better. Do not report style preferences as errors, and do not invent problems.

Verified Québec usage:
{lexicon}
{flags}
Lesson (JSON):
{lesson}

Answer with a single JSON object matching this JSON Schema:
{schema}"""


FLAGS = """
An automatic checker (a small model, often wrong) flagged the items below. Decide each one \
yourself: report it as an error only if it is a real problem; otherwise ignore it.
{items}
"""


def build_prompt(
    lesson: dict[str, object], ref: Reference, flags: list[dict[str, str]] | None = None
) -> str:
    lexicon = "\n".join(f"- {t.term}: {t.meaning} (France: {t.france})" for t in ref.quebec)
    lesson_data = {k: v for k, v in lesson.items() if k != "provenance"}
    items = "\n".join(f"- {f['path'].split(':', 1)[-1]}: {f['message']}" for f in flags or [])
    return PROMPT.format(
        level=lesson["level"],
        lexicon=lexicon or "(none)",
        flags=FLAGS.format(items=items) if items else "",
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
            build_prompt(job.output, ref, critic_flags(job)), encoding="utf-8"
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


def critic_flags(job: GenerationJob) -> list[dict[str, str]]:
    """Sentences the local AI critic flagged. It is often wrong, so the external reviewer
    decides each one (they are listed in its prompt) instead of the flags blocking anything."""
    return [v for v in job.validation if v["message"].startswith("AI critic")]


def needs_attention(job: GenerationJob) -> list[dict[str, str]]:
    """Warnings that must not be published without a revision or a human: Québec claims
    missing from the verified lexicon. Haiku misses these (it passed « avoir le feu au cul »
    as a Québec expression)."""
    return [v for v in job.validation if UNVERIFIED_QUEBEC in v["message"]]


def warning_notes(warnings: list[dict[str, str]]) -> tuple[str, list[str]]:
    notes = "\n".join(
        f"- {w['path'].split(':', 1)[-1]}: {w['message']} Fix: use only verified Québec usage "
        "(otherwise standard French, region common), and correct or replace the sentence."
        for w in warnings
    )
    targets = sorted({w["path"].split(":", 1)[-1] for w in warnings if ":" in w["path"]})
    return notes, targets


def validation_notes(job: GenerationJob) -> tuple[str, list[str]]:
    """Deterministic errors the draft still has, as revision notes."""
    errors = [v for v in job.validation if v["severity"] == "error"]
    notes = "\n".join(f"- {v['path'].split(':', 1)[-1]}: {v['message']}" for v in errors)
    targets = sorted(
        {v["path"].split(":", 1)[1].split(".", 1)[0] for v in errors if ":" in v["path"]}
    )
    return notes, targets


# --- Published lessons ----------------------------------------------------------------------
# Lessons published without an external proof-read (e.g. by a remote author's auto-review) can
# be reviewed afterwards: lesson-<id>.prompt.txt / .findings.json in the same folder. Findings
# with errors become a revision job, which then goes through the normal review.


def export_published(content_root: Path, lessons: list[Lesson]) -> Path:
    out = content_root / REVIEW_DIR
    out.mkdir(parents=True, exist_ok=True)
    ref = Reference.load(content_root)
    for lesson in lessons:
        assert lesson.published_revision is not None
        (out / f"lesson-{lesson.slug}.prompt.txt").write_text(
            build_prompt(lesson.published_revision.payload, ref), encoding="utf-8"
        )
    return out


def import_published_findings(
    content_root: Path, reviewer: str
) -> tuple[list[tuple[str, int, GenerationJob | None]], list[str]]:
    """Returns ([(lesson id, error count, revision job or None)], errors)."""
    from .services import create_job

    folder = content_root / REVIEW_DIR
    done: list[tuple[str, int, GenerationJob | None]] = []
    errors: list[str] = []
    for path in sorted(folder.glob("lesson-*.findings.json")):
        slug = path.name.removeprefix("lesson-").removesuffix(".findings.json")
        lesson = Lesson.objects.filter(slug=slug, published_revision__isnull=False).first()
        if lesson is None:
            errors.append(f"{path.name}: {slug} is not a published lesson")
            continue
        try:
            review = Review.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            errors.append(f"{path.name}: {exc.errors()[0]['msg']}")
            continue
        found = [f for f in review.issues if f.severity == "error"]
        job = None
        if found:
            notes = "\n".join(
                f"- {f.item_id} ({f.severity}): {f.problem} Fix: {f.suggested_fix}"
                for f in review.issues
            )
            job = create_job(
                lesson,
                kind=GenerationJob.Kind.REVISION,
                notes=f"Proof-read by {reviewer}:\n{notes}",
                targets=sorted({f.item_id for f in review.issues}),
            )
        for leftover in (path, folder / f"lesson-{slug}.prompt.txt"):
            leftover.unlink(missing_ok=True)
        done.append((slug, len(found), job))
    return done, errors
