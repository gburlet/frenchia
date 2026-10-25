from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from authoring.bank_workflow import promote
from curriculum import content
from curriculum.importer import import_content


class Command(BaseCommand):
    help = "Publish reviewed verb-bank and vocabulary drafts, then import them."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("ids", nargs="*")

    def handle(self, *args: Any, **options: Any) -> None:
        root = Path(settings.CONTENT_DIR)
        ref = content.reference()
        for kind in ("verbs", "vocabulary"):
            promoted, skipped = promote(root, ref, kind, options["ids"] or None)
            for item in promoted:
                self.stdout.write(f"published {kind}/{item}")
            for item in skipped:
                self.stdout.write(f"skipped {kind}/{item}")
        result = import_content(root)
        vocab = [c for c in result.created if c.startswith("vocabulary:")]
        self.stdout.write(f"imported {len(vocab)} vocabulary set(s); refused: {result.refused}")
