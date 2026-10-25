from typing import Any

from django.core.management.base import BaseCommand

from progress.models import ReviewSet


class Command(BaseCommand):
    help = "Mark review-set extras interrupted by a worker restart as failed (practice worker)."

    def handle(self, *args: Any, **options: Any) -> None:
        stale = ReviewSet.objects.filter(extras=ReviewSet.Extras.RUNNING).update(
            extras=ReviewSet.Extras.FAILED, extras_error="Interrupted (worker restarted)"
        )
        self.stdout.write(f"Marked {stale} interrupted review set(s) as failed")
