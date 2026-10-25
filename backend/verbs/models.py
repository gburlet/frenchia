from django.conf import settings
from django.db import models


class ConjugationAttempt(models.Model):
    """One typed conjugation, graded deterministically against the reference."""

    class Mode(models.TextChoices):
        FORM = "form"
        TABLE = "table"
        CONTEXT = "context"

    class Result(models.TextChoices):
        CORRECT = "correct"
        ACCENT = "accent", "Accents only"
        INCORRECT = "incorrect"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    infinitive = models.CharField(max_length=60)
    tense = models.CharField(max_length=40)
    person = models.CharField(max_length=4)
    mode = models.CharField(max_length=10, choices=Mode.choices)
    sentence = models.JSONField(
        null=True, blank=True, help_text="Snapshot of the context sentence (context mode)"
    )
    answer = models.CharField(max_length=200)
    expected = models.CharField(max_length=200)
    result = models.CharField(max_length=10, choices=Result.choices)
    diagnosis = models.CharField(max_length=20, blank=True)
    time_spent_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        return f"{self.user} · {self.infinitive} {self.tense} {self.person}: {self.result}"


class VerbMastery(models.Model):
    """Running accuracy per (verb, tense): drives drill selection and the weak-spots list."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    infinitive = models.CharField(max_length=60)
    tense = models.CharField(max_length=40)
    attempts = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    ewma = models.FloatField(default=0.0, help_text="0-1, recent-weighted score")
    last_practiced = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "infinitive", "tense"], name="unique_verb_mastery"
            )
        ]
        verbose_name_plural = "verb mastery"

    def __str__(self) -> str:
        return f"{self.user} · {self.infinitive} {self.tense}: {self.ewma:.2f}"
