from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from contentkit.validate import format_issues
from curriculum.importer import import_content


class Command(BaseCommand):
    help = (
        "Import content/ into the database (idempotent). Use --publish to make new versions live."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--publish", action="store_true", help="publish newly imported versions"
        )
        parser.add_argument(
            "--lesson", action="append", dest="lessons", help="limit to lesson id(s)"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        result = import_content(
            Path(settings.CONTENT_DIR),
            dry_run=options["dry_run"],
            publish=options["publish"],
            only=set(options["lessons"]) if options["lessons"] else None,
        )
        if result.issues:
            self.stdout.write(format_issues(result.issues))
        for key, items in result.summary().items():
            for item in items:
                self.stdout.write(f"{key:9s} {item}")
        prefix = "[dry run] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}created {len(result.created)}, unchanged {len(result.unchanged)}, "
            f"published {len(result.published)}, refused {len(result.refused)}"
        )
        if result.refused:
            raise CommandError("some content was refused")
