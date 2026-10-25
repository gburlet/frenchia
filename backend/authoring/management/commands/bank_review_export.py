from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

from authoring.bank_workflow import REVIEW_DIR, export_reviews
from curriculum import content


class Command(BaseCommand):
    help = "Write proof-reading prompts for unreviewed verb-bank and vocabulary drafts."

    def handle(self, *args: Any, **options: Any) -> None:
        root = Path(settings.CONTENT_DIR)
        stems = export_reviews(root, content.reference(), ("verbs", "vocabulary"))
        if not stems:
            self.stdout.write("No drafts are waiting for a review.")
            return
        self.stdout.write(f"Wrote {len(stems)} prompt(s) to content/{REVIEW_DIR}/:")
        for stem in stems:
            self.stdout.write(f"  {stem}.prompt.txt -> write {stem}.findings.json")
