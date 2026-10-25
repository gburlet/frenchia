from django.conf import settings
from django.db import models


class TutorThread(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tutor_threads"
    )
    title = models.CharField(max_length=200)
    context = models.JSONField(
        default=dict, help_text="{lesson_id, exercise_revision_id, attempt_id}"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title


class TutorMessage(models.Model):
    """One turn. Kept generic (role + content + context) so future modes such as a spoken
    conversation can reuse it."""

    class Role(models.TextChoices):
        USER = "user"
        ASSISTANT = "assistant"

    class Status(models.TextChoices):
        STREAMING = "streaming"
        COMPLETE = "complete"
        STOPPED = "stopped"
        ERROR = "error"

    thread = models.ForeignKey(TutorThread, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.COMPLETE)
    context = models.JSONField(
        default=dict, help_text="Context reference when the message was sent"
    )
    context_snapshot = models.TextField(blank=True, help_text="The context text given to the model")
    model = models.CharField(max_length=100, blank=True)
    first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:60]}"
