from django.conf import settings
from django.db import models

from curriculum.models import Lesson


class VocabSet(models.Model):
    """A word list: a themed set (content/vocabulary/sets/) or a published lesson's vocabulary."""

    class Kind(models.TextChoices):
        THEME = "theme"
        LESSON = "lesson"

    slug = models.SlugField(max_length=100, primary_key=True)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    level = models.CharField(max_length=2)
    title = models.CharField(max_length=200)
    title_en = models.CharField(max_length=200)
    order = models.PositiveIntegerField(default=0)
    lesson = models.ForeignKey(
        Lesson, on_delete=models.SET_NULL, null=True, blank=True, related_name="vocab_sets"
    )
    content_version = models.PositiveIntegerField(default=1)
    content_hash = models.CharField(max_length=64)
    source_path = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["order", "slug"]

    def __str__(self) -> str:
        return f"{self.slug} v{self.content_version}"


class Lexeme(models.Model):
    """One word of a set. Updated in place when its set gets a new version (cards keep their
    scheduling); never deleted: words dropped from a set are retired."""

    stable_id = models.CharField(max_length=200, unique=True)
    vocab_set = models.ForeignKey(VocabSet, on_delete=models.CASCADE, related_name="lexemes")
    order = models.PositiveIntegerField(default=0)
    fr = models.CharField(max_length=120)
    en = models.CharField(max_length=200)
    pos = models.CharField(max_length=12)
    gender = models.CharField(max_length=1, blank=True)
    plural = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=6, default="common")
    formality = models.CharField(max_length=10, default="standard")
    example_fr = models.TextField(blank=True)
    example_en = models.TextField(blank=True)
    note = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64)
    retired = models.BooleanField(default=False)

    class Meta:
        ordering = ["vocab_set", "order"]

    def __str__(self) -> str:
        return self.stable_id


class VocabCard(models.Model):
    """FSRS scheduling state for one learner, word and direction."""

    class Direction(models.TextChoices):
        RECOGNIZE = "recognize", "French → English"
        RECALL = "recall", "English → French"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    lexeme = models.ForeignKey(Lexeme, on_delete=models.CASCADE, related_name="cards")
    direction = models.CharField(max_length=10, choices=Direction.choices)
    fsrs = models.JSONField(default=dict, help_text="fsrs.Card.to_dict()")
    due = models.DateTimeField()
    reps = models.PositiveIntegerField(default=0)
    lapses = models.PositiveIntegerField(default=0)
    last_review = models.DateTimeField(null=True, blank=True)
    suspended = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "lexeme", "direction"], name="unique_vocab_card"
            )
        ]
        indexes = [models.Index(fields=["user", "suspended", "due"])]

    def __str__(self) -> str:
        return f"{self.user} · {self.lexeme_id} ({self.direction})"


class VocabReview(models.Model):
    class Rating(models.IntegerChoices):
        AGAIN = 1
        HARD = 2
        GOOD = 3
        EASY = 4

    card = models.ForeignKey(VocabCard, on_delete=models.CASCADE, related_name="reviews")
    rating = models.PositiveSmallIntegerField(choices=Rating.choices)
    reviewed_at = models.DateTimeField()
    duration_ms = models.PositiveIntegerField(null=True, blank=True)
    answer = models.CharField(max_length=200, blank=True)
    check_result = models.CharField(max_length=12, blank=True)
    was_new = models.BooleanField(default=False)
    due_before = models.DateTimeField()

    class Meta:
        indexes = [models.Index(fields=["card", "-reviewed_at"])]

    def __str__(self) -> str:
        return f"{self.card} · {self.rating}"
