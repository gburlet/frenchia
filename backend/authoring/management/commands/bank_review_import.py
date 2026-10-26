from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from authoring.bank_workflow import import_reviews
from authoring.bankgen import BankGenerator
from curriculum import content
from inference.providers import get_authoring_chat_model


class Command(BaseCommand):
    help = "Apply proof-reader findings to verb-bank and vocabulary drafts."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--reviewer", default="claude-haiku")
        parser.add_argument(
            "--revise", action="store_true", help="let the local LLM fix flagged items"
        )

    def handle(self, *args: Any, **options: Any) -> None:
        ref = content.reference()
        generator = (
            BankGenerator(chat := get_authoring_chat_model(), ref, model_name=chat.model)
            if options["revise"]
            else None
        )
        outcomes = import_reviews(Path(settings.CONTENT_DIR), ref, options["reviewer"], generator)
        if not outcomes:
            self.stdout.write("No findings to import.")
        for o in outcomes:
            state = "reviewed" if o.reviewed else "needs another review" if o.revised else "-"
            line = f"{o.stem}: {o.errors} errors, {o.suggestions} suggestions; {state}"
            if o.revised:
                line += f"; revised {', '.join(o.revised)}"
            if o.dropped:
                line += f"; dropped {', '.join(o.dropped)}"
            if o.problem:
                line += f"; {o.problem}"
            self.stdout.write(line)
