"""Learner attempts. An attempt points at the immutable ExerciseRevision it was answered
against and also snapshots that payload, so history survives any later content change."""

from django.conf import settings
from django.db import models

from curriculum.models import ExerciseRevision, GrammarTopic


class ExerciseAttempt(models.Model):
    class Status(models.TextChoices):
        GRADED = "graded"
        PENDING = "pending", "Pending (LLM unavailable)"

    class Grading(models.TextChoices):
        DETERMINISTIC = "deterministic"
        LLM = "llm"
        PENDING = "pending"
        DISPUTE = "dispute", "Accepted after dispute"

    class Verdict(models.TextChoices):
        CORRECT = "correct"
        ACCEPTABLE = "acceptable"
        INCORRECT = "incorrect"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="attempts"
    )
    exercise_revision = models.ForeignKey(
        ExerciseRevision, on_delete=models.PROTECT, related_name="attempts"
    )
    answer = models.TextField()
    prompt_snapshot = models.JSONField(help_text="The exercise payload, answers included")
    status = models.CharField(max_length=10, choices=Status.choices)
    grading = models.CharField(max_length=15, choices=Grading.choices)
    verdict = models.CharField(max_length=12, choices=Verdict.choices, blank=True, default="")
    score = models.PositiveSmallIntegerField(null=True, blank=True)
    feedback = models.JSONField(default=dict)
    model = models.CharField(max_length=100, blank=True)
    prompt_version = models.CharField(max_length=20, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    time_spent_ms = models.PositiveIntegerField(null=True, blank=True)
    disputed = models.BooleanField(default=False)
    dispute_comment = models.TextField(blank=True)
    dispute_resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "-created_at"])]

    def __str__(self) -> str:
        outcome = self.verdict or self.status
        return f"Attempt {self.pk} on {self.exercise_revision.exercise_id} ({outcome})"


class MistakeOccurrence(models.Model):
    """One error found in an attempt: the raw material for recurring-mistake tracking."""

    attempt = models.ForeignKey(ExerciseAttempt, on_delete=models.CASCADE, related_name="mistakes")
    category = models.CharField(max_length=30)
    grammar_topic = models.ForeignKey(
        GrammarTopic, on_delete=models.SET_NULL, null=True, blank=True
    )
    span = models.CharField(max_length=300, blank=True)
    explanation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.category}: {self.span}"
