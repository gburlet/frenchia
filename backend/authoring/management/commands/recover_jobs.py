from functools import partial
from typing import Any

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from authoring.models import GenerationJob


class Command(BaseCommand):
    help = (
        "Requeue generation jobs left 'running' by a stopped worker. Run at worker start: with a "
        "single worker, any job still marked running at that moment was interrupted."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        from authoring.tasks import run_generation_job

        stale = list(GenerationJob.objects.filter(status=GenerationJob.Status.RUNNING))
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
