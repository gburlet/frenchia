from django.db import models

from curriculum.models import Lesson


class GenerationJob(models.Model):
    """One request to the local LLM to generate or revise a lesson, and its review outcome."""

    class Kind(models.TextChoices):
        LESSON = "lesson", "Generate lesson"
        REVISION = "revision", "Revise lesson"

    class Status(models.TextChoices):
        QUEUED = "queued"
        RUNNING = "running"
        FAILED = "failed"
        NEEDS_REVIEW = "needs_review", "Needs review"
        APPROVED = "approved"
        REJECTED = "rejected"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.LESSON)
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="generation_jobs")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    parent = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True)
    notes = models.TextField(blank=True, help_text="Revision instructions for the LLM")
    targets = models.JSONField(default=list, blank=True, help_text="Section/exercise ids to revise")
    base_hash = models.CharField(
        max_length=64, blank=True, help_text="Hash of the lesson file when the job was created"
    )
    model = models.CharField(max_length=100, blank=True)
    prompts = models.JSONField(default=dict, blank=True)
    output = models.JSONField(null=True, blank=True, help_text="Generated lesson (canonical data)")
    draft_path = models.CharField(max_length=300, blank=True)
    validation = models.JSONField(default=list, blank=True)
    progress = models.JSONField(default=list, blank=True)
    error = models.TextField(blank=True)
    llm_calls = models.PositiveIntegerField(default=0)
    llm_seconds = models.FloatField(default=0)
    completion_tokens = models.PositiveIntegerField(default=0)
    reviewer_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Job {self.pk}: {self.get_kind_display()} {self.lesson_id} ({self.status})"

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.validation if issue["severity"] == "error")
