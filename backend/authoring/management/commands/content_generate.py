from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from authoring.models import GenerationJob
from authoring.services import create_job, run_job
from curriculum.models import Lesson


class Command(BaseCommand):
    help = "Generate a lesson draft with the local LLM (review it in Django Admin)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("lesson")
        parser.add_argument("--sync", action="store_true", help="run here instead of the worker")

    def handle(self, *args: Any, **options: Any) -> None:
        lesson = Lesson.objects.filter(slug=options["lesson"]).first()
        if lesson is None:
            raise CommandError(f"unknown lesson {options['lesson']!r}; run content_import first")
        job = create_job(lesson, enqueue=not options["sync"])
        if not options["sync"]:
            self.stdout.write(f"Queued job {job.pk}; follow it in Admin → Generation jobs")
            return
        job = run_job(job.pk)
        for step in job.progress:
            self.stdout.write(f"  {step['at']}  {step['message']}")
        if job.status == GenerationJob.Status.FAILED:
            raise CommandError(job.error.splitlines()[0])
        for issue in job.validation:
            self.stdout.write(
                f"  {issue['severity'].upper():7s} {issue['path']}: {issue['message']}"
            )
        self.stdout.write(
            f"Job {job.pk}: {job.status}, draft {job.draft_path}, {job.llm_calls} LLM calls, "
            f"{job.llm_seconds:.0f}s, {job.completion_tokens} tokens"
        )
