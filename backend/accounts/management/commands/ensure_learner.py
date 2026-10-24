import environ
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

REQUIRED = ("FRENCHIA_ADMIN_USERNAME", "FRENCHIA_ADMIN_PASSWORD", "FRENCHIA_ADMIN_EMAIL")


class Command(BaseCommand):
    help = "Create or update the superuser from FRENCHIA_ADMIN_* environment variables."

    def handle(self, *args: object, **options: object) -> None:
        env = environ.Env()
        values = {name: env.str(name, default="").strip() for name in REQUIRED}
        missing = [name for name, value in values.items() if not value]
        if missing:
            raise CommandError(f"Missing required environment variables: {', '.join(missing)}")

        User = get_user_model()
        user, created = User.objects.get_or_create(username=values["FRENCHIA_ADMIN_USERNAME"])
        user.email = values["FRENCHIA_ADMIN_EMAIL"]
        user.is_staff = True
        user.is_superuser = True
        user.set_password(values["FRENCHIA_ADMIN_PASSWORD"])
        user.save()
        self.stdout.write(
            self.style.SUCCESS(f"{'Created' if created else 'Updated'} user '{user.username}'.")
        )
