from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from authoring.critic import check_blanks, critique, solve_choices
from authoring.models import GenerationJob
from authoring.services import create_job
from contentkit.models import Lesson as LessonContent
from contentkit.reference import Reference
from contentkit.validate import check_lesson_quality
from curriculum.models import Lesson
from inference.providers import get_authoring_chat_model


class Command(BaseCommand):
    help = (
        "Re-check published lessons with today's deterministic checks and the authoring "
        "model's critic, solver and blank checker; --revise queues a revision for each lesson "
        "with problems (auto-reviewed like any revision)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("lessons", nargs="*", help="lesson ids (default: all published)")
        parser.add_argument("--level", action="append", default=[])
        parser.add_argument("--revise", action="store_true")

    def handle(self, *args: Any, **options: Any) -> None:
        chat = get_authoring_chat_model()
        ref = Reference.load(Path(settings.CONTENT_DIR))
        lessons = Lesson.objects.filter(published_revision__isnull=False).select_related(
            "published_revision"
        )
        if options["lessons"]:
            lessons = lessons.filter(slug__in=options["lessons"])
        if options["level"]:
            lessons = lessons.filter(unit__level__in=options["level"])
        for lesson in lessons.order_by("unit__level", "order"):
            assert lesson.published_revision is not None
            content = LessonContent.model_validate(lesson.published_revision.payload)
            issues = [i for i in check_lesson_quality(content, ref) if i.severity == "error"]
            issues += critique(chat, content)
            issues += solve_choices(chat, content)
            issues += check_blanks(chat, content, list(content.objectives))
            if not issues:
                self.stdout.write(f"{lesson.slug}: ok")
                continue
            self.stdout.write(f"{lesson.slug}: {len(issues)} problem(s)")
            for issue in issues:
                self.stdout.write(f"  {issue.path.split(':', 1)[-1]}: {issue.message[:200]}")
            if options["revise"]:
                notes = "\n".join(
                    f"- {i.path.split(':', 1)[-1]}: {i.message} Fix it if it is a real error."
                    for i in issues
                )
                targets = sorted({i.path.split(":", 1)[1].split(".", 1)[0] for i in issues})
                job = create_job(
                    lesson, kind=GenerationJob.Kind.REVISION, notes=notes, targets=targets
                )
                self.stdout.write(f"  -> revision job {job.pk}")
