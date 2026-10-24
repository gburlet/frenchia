from django.core.management.base import CommandParser

from .content_publish import Command as PublishCommand


class Command(PublishCommand):
    help = "Roll a lesson back to an earlier imported version (alias of content_publish --version)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("lesson")
        parser.add_argument("--to", type=int, required=True, dest="version")
