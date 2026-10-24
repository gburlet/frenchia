"""Database projection of the version-controlled content in content/.

Files own the content; these tables hold what was imported, which revision is live, and
stable rows for learner data to point at. Revisions are immutable: learner attempts reference
an ExerciseRevision, so regenerating a lesson creates new revisions instead of changing the
content a past attempt was graded against."""

from typing import Any, ClassVar

from django.db import models


class Level(models.TextChoices):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ImmutableFieldsMixin(models.Model):
    """Refuse to change selected fields once a row exists."""

    immutable_fields: ClassVar[tuple[str, ...]] = ()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None and not self._state.adding:
            stored = (
                type(self)
                ._default_manager.filter(pk=self.pk)
                .values(*self.immutable_fields)
                .first()
            )
            if stored is not None:
                changed = [f for f in self.immutable_fields if stored[f] != getattr(self, f)]
                if changed:
                    raise ValueError(f"{type(self).__name__} is immutable: {', '.join(changed)}")
        super().save(*args, **kwargs)


class CurriculumLevel(models.Model):
    code = models.CharField(primary_key=True, max_length=2, choices=Level.choices)
    title = models.CharField(max_length=100)
    summary = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self) -> str:
        return f"{self.code} · {self.title}"


class GrammarTopic(models.Model):
    slug = models.SlugField(primary_key=True, max_length=80)
    level = models.CharField(max_length=2, choices=Level.choices)
    title = models.CharField(max_length=200)
    related = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["level", "slug"]

    def __str__(self) -> str:
        return self.title


class Unit(models.Model):
    slug = models.SlugField(primary_key=True, max_length=80)
    level = models.CharField(max_length=2, choices=Level.choices)
    order = models.PositiveIntegerField()
    title = models.CharField(max_length=200)
    objectives = models.JSONField(default=list)

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.level} · {self.title}"


class Lesson(models.Model):
    """A curriculum slot. Exists as soon as it is outlined, before any content is written."""

    slug = models.SlugField(primary_key=True, max_length=80)
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name="lessons")
    order = models.PositiveIntegerField(help_text="Position in the whole curriculum")
    kind = models.CharField(max_length=20)
    title = models.CharField(max_length=200)
    outline = models.JSONField(help_text="The lesson outline from content/curriculum/")
    grammar_topics = models.ManyToManyField(GrammarTopic, related_name="lessons", blank=True)
    published_revision = models.ForeignKey(
        "LessonRevision",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return f"{self.slug}: {self.title}"

    @property
    def level(self) -> str:
        return self.unit.level


class ContentImport(models.Model):
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    dry_run = models.BooleanField(default=False)
    ok = models.BooleanField(default=False)
    git_sha = models.CharField(max_length=40, blank=True)
    summary = models.JSONField(default=dict)
    issues = models.JSONField(default=list)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"Import {self.pk} ({'ok' if self.ok else 'failed'})"


class LessonRevision(ImmutableFieldsMixin):
    immutable_fields = ("lesson_id", "content_version", "content_hash", "payload")

    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="revisions")
    content_version = models.PositiveIntegerField()
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    source_path = models.CharField(max_length=300)
    is_manually_edited = models.BooleanField(default=False)
    content_import = models.ForeignKey(
        ContentImport, on_delete=models.PROTECT, null=True, blank=True
    )
    imported_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["lesson", "-content_version"]
        constraints = [
            models.UniqueConstraint(
                fields=["lesson", "content_version"], name="unique_lesson_version"
            )
        ]

    def __str__(self) -> str:
        return f"{self.lesson_id} v{self.content_version}"

    @property
    def status(self) -> str:
        if self.lesson.published_revision_id == self.pk:
            return "published"
        return "superseded" if self.published_at else "imported"


class Exercise(models.Model):
    """Stable identity of an exercise across lesson versions: "<lesson>/<id>"."""

    stable_id = models.CharField(primary_key=True, max_length=120)
    lesson = models.ForeignKey(Lesson, on_delete=models.PROTECT, related_name="exercises")
    kind = models.CharField(max_length=20)

    def __str__(self) -> str:
        return self.stable_id


class ExerciseRevision(ImmutableFieldsMixin):
    immutable_fields = ("exercise_id", "lesson_revision_id", "content_hash", "payload", "origin")

    class Origin(models.TextChoices):
        CURRICULUM = "curriculum"
        PERSONALIZED = "personalized"

    exercise = models.ForeignKey(Exercise, on_delete=models.PROTECT, related_name="revisions")
    lesson_revision = models.ForeignKey(
        LessonRevision, on_delete=models.PROTECT, related_name="exercise_revisions"
    )
    content_hash = models.CharField(max_length=64)
    payload = models.JSONField()
    origin = models.CharField(max_length=20, choices=Origin.choices, default=Origin.CURRICULUM)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["exercise", "lesson_revision"], name="unique_exercise_per_revision"
            )
        ]

    def __str__(self) -> str:
        return f"{self.exercise_id} @ v{self.lesson_revision.content_version}"
