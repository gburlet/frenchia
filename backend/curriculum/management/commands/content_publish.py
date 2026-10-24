from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser

from curriculum.importer import publish_revision
from curriculum.models import Lesson


class Command(BaseCommand):
    help = "Publish a lesson version (default: the latest imported). Also used for rollback."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("lesson")
        parser.add_argument("--version", type=int, help="content_version to publish")

    def handle(self, *args: Any, **options: Any) -> None:
        lesson = Lesson.objects.filter(slug=options["lesson"]).first()
        if lesson is None:
            raise CommandError(f"unknown lesson {options['lesson']!r}")
        revisions = lesson.revisions.order_by("-content_version")
        revision = (
            revisions.filter(content_version=options["version"]).first()
            if options["version"]
            else revisions.first()
        )
        if revision is None:
            raise CommandError("no such imported version; run content_import first")
        previous = lesson.published_revision
        publish_revision(revision)
        was = f" (was v{previous.content_version})" if previous else ""
        self.stdout.write(f"published {lesson.slug} v{revision.content_version}{was}")
