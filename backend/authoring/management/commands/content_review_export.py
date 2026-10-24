from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from authoring.external_review import export, pending_jobs
from authoring.models import GenerationJob


class Command(BaseCommand):
    help = "Write proof-reading prompts for generated lessons awaiting review (ADR 0003)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--job", type=int, action="append", help="specific job id(s)")

    def handle(self, *args: Any, **options: Any) -> None:
        jobs = (
            list(GenerationJob.objects.filter(pk__in=options["job"]))
            if options["job"]
            else pending_jobs()
        )
        if not jobs:
            self.stdout.write("No generated lessons are waiting for an external review.")
            return
        folder = export(Path(settings.CONTENT_DIR), jobs)
        self.stdout.write(
            f"Wrote {len(jobs)} prompt(s) to content/{folder.relative_to(settings.CONTENT_DIR)}/:"
        )
        for job in jobs:
            self.stdout.write(
                f"  job-{job.pk}.prompt.txt  ({job.lesson_id}) -> write job-{job.pk}.findings.json"
            )
