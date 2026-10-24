from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    """Custom user model, kept swappable-ready for future fields."""
