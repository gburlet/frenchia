from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from authoring.external_review import (
    import_findings,
    needs_attention,
    revision_notes,
    warning_notes,
)
from authoring.models import GenerationJob
from authoring.services import ReviewError, approve, request_revision


def _round(job: GenerationJob) -> int:
    """How many generations led to this job (1 for a fresh draft)."""
    depth = 1
    while job.parent_id is not None:
        job, depth = job.parent, depth + 1  # type: ignore[assignment]
    return depth


class Command(BaseCommand):
    help = "Attach external proof-reading findings to their generation jobs (ADR 0003)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reviewer", required=True, help="e.g. claude-haiku-5-5")
        parser.add_argument(
            "--revise", action="store_true", help="queue an LLM revision for jobs with findings"
        )
        parser.add_argument(
            "--approve-clean",
            action="store_true",
            help="publish drafts with no reviewer or validation errors and no unverified Québec "
            "claims (reviewer suggestions are ignored)",
        )
        parser.add_argument(
            "--max-rounds",
            type=int,
            default=4,
            help="with --revise, leave a draft for manual review after this many generations",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        imported, errors = import_findings(Path(settings.CONTENT_DIR), options["reviewer"])
        for job_id in imported:
            job = GenerationJob.objects.get(pk=job_id)
            counts = {
                s: sum(f["severity"] == s for f in job.external_review)
                for s in ("error", "suggestion")
            }
            line = (
                f"job {job_id} ({job.lesson_id}): "
                f"{counts['error']} errors, {counts['suggestion']} suggestions"
            )
            clean = not counts["error"] and not job.error_count
            attention = needs_attention(job)
            if options["approve_clean"] and clean and not attention:
                try:
                    line += f" -> approved {approve(job).name}"
                except ReviewError as exc:
                    line += f" -> not approved: {exc}"
            elif options["revise"] and (job.external_review or attention):
                if attention:
                    line += f", {len(attention)} unverified Québec claims"
                if _round(job) >= options["max_rounds"]:
                    line += f" -> left for manual review after {options['max_rounds']} rounds"
                else:
                    notes, targets = revision_notes(job)
                    extra_notes, extra_targets = warning_notes(attention)
                    notes = "\n".join(n for n in (notes, extra_notes) if n)
                    child = request_revision(job, notes, sorted({*targets, *extra_targets}))
                    line += f" -> revision job {child.pk} queued"
            self.stdout.write(line)
        for error in errors:
            self.stderr.write(error)
        if errors:
            raise CommandError(f"{len(errors)} file(s) not imported")
