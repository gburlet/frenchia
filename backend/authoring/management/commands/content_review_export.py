from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from authoring.external_review import export, export_published, pending_jobs
from authoring.models import GenerationJob
from curriculum.models import Lesson


class Command(BaseCommand):
    help = "Write proof-reading prompts for generated lessons awaiting review (ADR 0003)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--job", type=int, action="append", help="specific job id(s)")
        parser.add_argument(
            "--published",
            nargs="*",
            metavar="LESSON",
            help="also review published lessons (all, or these ids) with no job in progress",
        )
        parser.add_argument("--level", action="append", default=[], help="with --published")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["published"] is not None:
            self._published(options["published"], options["level"])
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

    def _published(self, slugs: list[str], levels: list[str]) -> None:
        busy = GenerationJob.objects.filter(
            status__in=["queued", "running", "needs_review"]
        ).values_list("lesson", flat=True)
        lessons = Lesson.objects.filter(published_revision__isnull=False).exclude(slug__in=busy)
        if slugs:
            lessons = lessons.filter(slug__in=slugs)
        if levels:
            lessons = lessons.filter(unit__level__in=levels)
        chosen = list(lessons.select_related("published_revision").order_by("order"))
        export_published(Path(settings.CONTENT_DIR), chosen)
        self.stdout.write(f"Wrote {len(chosen)} published-lesson prompt(s):")
        for lesson in chosen:
            self.stdout.write(
                f"  lesson-{lesson.slug}.prompt.txt -> write lesson-{lesson.slug}.findings.json"
            )
