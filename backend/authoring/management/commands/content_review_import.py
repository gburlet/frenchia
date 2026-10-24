from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from authoring.external_review import import_findings, revision_notes
from authoring.models import GenerationJob
from authoring.services import request_revision


class Command(BaseCommand):
    help = "Attach external proof-reading findings to their generation jobs (ADR 0003)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reviewer", required=True, help="e.g. claude-haiku-5-5")
        parser.add_argument(
            "--revise", action="store_true", help="queue an LLM revision for jobs with findings"
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
            if options["revise"] and job.external_review:
                notes, targets = revision_notes(job)
                child = request_revision(job, notes, targets)
                line += f" -> revision job {child.pk} queued"
            self.stdout.write(line)
        for error in errors:
            self.stderr.write(error)
        if errors:
            raise CommandError(f"{len(errors)} file(s) not imported")
