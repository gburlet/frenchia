from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from contentkit.validate import format_issues, validate_repository


class Command(BaseCommand):
    help = "Validate content files (schemas, references, deterministic quality checks)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--no-quality", action="store_true", help="schema and references only")

    def handle(self, *args: Any, **options: Any) -> None:
        repo = validate_repository(Path(settings.CONTENT_DIR), quality=not options["no_quality"])
        if repo.issues:
            self.stdout.write(format_issues(repo.issues))
        self.stdout.write(
            f"{len(repo.lessons)} lesson files, {len(repo.outlines)} outlined lessons: "
            f"{len(repo.errors)} errors, {len(repo.issues) - len(repo.errors)} warnings"
        )
        if repo.errors:
            raise CommandError("content has errors")
