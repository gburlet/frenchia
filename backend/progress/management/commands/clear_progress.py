from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.db.models import Model

from exercises.models import ExerciseAttempt
from progress.models import LessonProgress, ReviewSet, TopicMastery
from verbs.models import ConjugationAttempt, VerbMastery
from vocabulary.models import VocabCard

# Deleting these cascades to mistakes (from attempts), review items and vocab reviews.
# The account, its profile settings and tutor threads are kept.
LEARNER_DATA: tuple[type[Model], ...] = (
    ExerciseAttempt,
    LessonProgress,
    TopicMastery,
    ReviewSet,
    ConjugationAttempt,
    VerbMastery,
    VocabCard,
)


class Command(BaseCommand):
    help = (
        "Clear one user's learning progress "
        "(lessons, attempts, mastery, review sets, verb and vocab drills)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("username")
        parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted.")
        parser.add_argument("--noinput", "--no-input", action="store_false", dest="interactive")

    def handle(self, *args: Any, **options: Any) -> None:
        username = options["username"]
        try:
            user = get_user_model().objects.get(username=username)
        except get_user_model().DoesNotExist:
            raise CommandError(f"No user named '{username}'.") from None

        counts = {
            model.__name__: model._default_manager.filter(user=user).count()
            for model in LEARNER_DATA
        }
        for name, count in counts.items():
            self.stdout.write(f"  {name}: {count}")
        if not any(counts.values()):
            self.stdout.write(f"'{username}' has no progress to clear.")
            return
        if options["dry_run"]:
            self.stdout.write("Dry run: nothing deleted.")
            return
        if options["interactive"]:
            answer = input(f"Delete all progress for '{username}'? Type the username to confirm: ")
            if answer.strip() != username:
                raise CommandError("Cancelled.")

        with transaction.atomic():
            deleted: dict[str, int] = {}
            for model in LEARNER_DATA:
                _, per_model = model._default_manager.filter(user=user).delete()
                for label, count in per_model.items():
                    deleted[label] = deleted.get(label, 0) + count
        summary = ", ".join(
            f"{count} {label.split('.')[-1]}" for label, count in deleted.items() if count
        )
        self.stdout.write(self.style.SUCCESS(f"Cleared progress for '{username}': {summary}."))
