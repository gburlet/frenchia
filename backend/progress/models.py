from django.conf import settings
from django.db import models

from curriculum.models import GrammarTopic, Lesson, LessonRevision


class LessonProgress(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name="progress")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_revision = models.ForeignKey(
        LessonRevision, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "lesson"], name="unique_lesson_progress")
        ]

    def __str__(self) -> str:
        return f"{self.user} · {self.lesson_id}: {self.status}"


class TopicMastery(models.Model):
    """Running accuracy per grammar topic (exponentially weighted, recent attempts count more)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topic = models.ForeignKey(GrammarTopic, on_delete=models.CASCADE, related_name="mastery")
    attempts = models.PositiveIntegerField(default=0)
    correct = models.PositiveIntegerField(default=0)
    ewma = models.FloatField(default=0.0, help_text="0-1, recent-weighted score")
    last_practiced = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["user", "topic"], name="unique_topic_mastery")
        ]
        verbose_name_plural = "topic mastery"

    def __str__(self) -> str:
        return f"{self.user} · {self.topic_id}: {self.ewma:.2f}"


class ReviewSet(models.Model):
    """A personalized practice session: curriculum exercises on the learner's weakest topics,
    plus exercises the local LLM writes around their recent mistakes (added when ready)."""

    class Extras(models.TextChoices):
        NONE = "none"
        QUEUED = "queued"
        RUNNING = "running"
        READY = "ready"
        FAILED = "failed"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    topics = models.JSONField(default=list, help_text="[{id, title, reason}] at creation")
    extras = models.CharField(max_length=10, choices=Extras.choices, default=Extras.NONE)
    extras_error = models.TextField(blank=True)
    extras_log = models.JSONField(default=list, blank=True, help_text="Dropped items and stats")
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.user} · review {self.pk}"


class ReviewItem(models.Model):
    class Source(models.TextChoices):
        MISSED = "missed", "answered wrong last time"
        UNSEEN = "unseen", "not tried yet"
        REFRESH = "refresh", "practised a while ago"
        GENERATED = "generated", "AI-generated for you"

    review_set = models.ForeignKey(ReviewSet, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveSmallIntegerField()
    exercise_revision = models.ForeignKey(
        "curriculum.ExerciseRevision", on_delete=models.PROTECT, related_name="review_items"
    )
    topic = models.ForeignKey(GrammarTopic, on_delete=models.PROTECT, related_name="+")
    source = models.CharField(max_length=10, choices=Source.choices)

    class Meta:
        ordering = ["review_set", "order"]
        constraints = [
            models.UniqueConstraint(
                fields=["review_set", "exercise_revision"], name="unique_review_item"
            )
        ]

    def __str__(self) -> str:
        return f"{self.review_set} #{self.order}"
