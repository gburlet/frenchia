from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user model, kept swappable-ready for future fields."""


class LearnerProfile(models.Model):
    """Learner settings used to personalise grading, the tutor and review."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    level = models.CharField(max_length=2, default="A2")
    target_level = models.CharField(max_length=2, default="B2")
    region = models.CharField(max_length=10, default="qc", help_text="qc = Québec-first")
    explanation_language = models.CharField(max_length=5, default="en")
    tts_speed = models.FloatField(default=1.0)

    def __str__(self) -> str:
        return f"{self.user} ({self.level} → {self.target_level})"

    @classmethod
    def for_user(cls, user: User) -> "LearnerProfile":
        profile, _ = cls.objects.get_or_create(user=user)
        return profile
