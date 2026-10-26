from datetime import datetime, timedelta
from functools import partial
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import transaction
from django.utils import timezone

from authoring.models import GenerationJob

QUIET_FOR = timedelta(minutes=10)


def _last_activity(job: GenerationJob) -> datetime:
    if job.progress:
        return datetime.fromisoformat(job.progress[-1]["at"])
    return job.started_at or job.created_at


class Command(BaseCommand):
    help = (
        "Requeue generation jobs left 'running' by a stopped worker. Run at worker start: with a "
        "single worker, any job still marked running at that moment was interrupted; with "
        "several, only jobs quiet for 10 minutes are."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--all",
            action="store_true",
            help="requeue every running job (only while no worker is running)",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        from authoring.tasks import run_generation_job

        # With several workers, another worker may be running a job right now: only jobs that
        # have shown no progress for a while were interrupted.
        cutoff = timezone.now() - (timedelta(0) if options["all"] else QUIET_FOR)
        stale = [
            job
            for job in GenerationJob.objects.filter(status=GenerationJob.Status.RUNNING)
            if _last_activity(job) < cutoff
        ]
        for job in stale:
            note = {
                "at": timezone.now().isoformat(timespec="seconds"),
                "message": "Interrupted (worker restarted); requeued from the start",
            }
            with transaction.atomic():
                GenerationJob.objects.filter(pk=job.pk).update(
                    status=GenerationJob.Status.QUEUED,
                    started_at=None,
                    progress=[*job.progress, note],
                )
                # It was already running, so it was next in line: keep it ahead of the queue.
                task = run_generation_job.using(priority=100)
                transaction.on_commit(partial(task.enqueue, job.pk))
        self.stdout.write(f"Requeued {len(stale)} interrupted generation job(s)")
