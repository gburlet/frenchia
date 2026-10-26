from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from authoring.external_review import (
    import_findings,
    import_published_findings,
    needs_attention,
    revision_notes,
    validation_notes,
    warning_notes,
)
from authoring.models import GenerationJob
from authoring.services import (
    ReviewError,
    approve,
    generation_round,
    request_revision,
    revalidate,
)


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
        published, published_errors = import_published_findings(
            Path(settings.CONTENT_DIR), options["reviewer"]
        )
        for slug, count, job in published:
            outcome = f"revision job {job.pk} queued" if job else "no errors"
            self.stdout.write(f"published {slug}: {count} errors -> {outcome}")
        imported, errors = import_findings(Path(settings.CONTENT_DIR), options["reviewer"])
        errors += published_errors
        for job_id in imported:
            job = GenerationJob.objects.get(pk=job_id)
            revalidate(job)
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
            elif options["revise"] and (job.external_review or attention or job.error_count):
                if attention:
                    line += f", {len(attention)} unverified Québec claims"
                # A lesson that is already live gets more rounds: each draft is usually better
                # than the published version, which stays up while it converges.
                limit = options["max_rounds"] + (2 if job.lesson.published_revision_id else 0)
                if generation_round(job) >= limit:
                    # The learner's rule: after the last round, publish rather than wait in
                    # Admin (each round is usually better than the live version).
                    try:
                        path = approve(job, allow_errors=True)
                        line += f" -> published after {limit} rounds: {path.name}"
                    except ReviewError as exc:
                        line += f" -> not published after {limit} rounds: {exc}"
                else:
                    # Errors only: rewriting for every suggestion introduced new errors.
                    parts = [
                        revision_notes(job, include_suggestions=False),
                        warning_notes(attention),
                        validation_notes(job),
                    ]
                    notes = "\n".join(n for n, _ in parts if n)
                    targets = sorted({t for _, ts in parts for t in ts})
                    child = request_revision(job, notes, targets)
                    line += f" -> revision job {child.pk} queued"
            self.stdout.write(line)
        for error in errors:
            self.stderr.write(error)
        if errors:
            raise CommandError(f"{len(errors)} file(s) not imported")
