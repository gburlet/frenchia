import json
from typing import Any

from django.contrib import admin, messages
from django.db.models import Count, OuterRef, QuerySet, Subquery
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

from authoring.models import GenerationJob
from authoring.services import create_job
from contentkit.yamlio import dump_yaml

from .importer import publish_revision
from .models import (
    ContentImport,
    Exercise,
    ExerciseRevision,
    GrammarTopic,
    Lesson,
    LessonRevision,
    Unit,
)


def render_preview(payload: dict[str, Any] | None) -> SafeString:
    if not payload:
        return mark_safe("<p>No content.</p>")  # noqa: S308
    return mark_safe(render_to_string("curriculum/lesson_preview.html", {"lesson": payload}))  # noqa: S308


def admin_link(obj: Any) -> SafeString:
    label = str(obj)
    url = reverse(f"admin:{obj._meta.app_label}_{obj._meta.model_name}_change", args=[obj.pk])
    return format_html('<a href="{}">{}</a>', url, label)


class ReadOnlyAdmin(admin.ModelAdmin):
    """Content comes from files: browse only."""

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Lesson)
class LessonAdmin(ReadOnlyAdmin):
    list_display = (
        "slug",
        "title",
        "level_display",
        "kind",
        "published_version",
        "revision_count",
        "latest_job_status",
    )
    list_filter = ("unit__level", "kind")
    search_fields = ("slug", "title")
    actions = ["generate_content"]
    fields = (
        "slug",
        "unit",
        "order",
        "kind",
        "title",
        "outline_display",
        "grammar_topics",
        "revisions_list",
        "published_preview",
    )
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lesson]:
        latest = GenerationJob.objects.filter(lesson=OuterRef("pk")).order_by("-created_at", "-pk")
        return (
            super()
            .get_queryset(request)
            .select_related("unit", "published_revision")
            .annotate(
                _revisions=Count("revisions", distinct=True),
                _latest_job=Subquery(latest.values("status")[:1]),
            )
        )

    @admin.display(description="Level", ordering="unit__level")
    def level_display(self, obj: Lesson) -> str:
        return obj.level

    @admin.display(description="Published")
    def published_version(self, obj: Lesson) -> str:
        rev = obj.published_revision
        return f"v{rev.content_version}" if rev else "-"

    @admin.display(description="Revisions", ordering="_revisions")
    def revision_count(self, obj: Any) -> int:
        return int(obj._revisions)

    @admin.display(description="Latest job", ordering="_latest_job")
    def latest_job_status(self, obj: Any) -> str:
        return str(obj._latest_job or "-")

    @admin.display(description="Outline")
    def outline_display(self, obj: Lesson) -> str:
        return format_html("<pre>{}</pre>", json.dumps(obj.outline, indent=2, ensure_ascii=False))

    @admin.display(description="Revisions")
    def revisions_list(self, obj: Lesson) -> SafeString:
        revs = obj.revisions.all()
        if not revs:
            return mark_safe("No revisions yet.")  # noqa: S308
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "",
                "<li>{} ({}){}</li>",
                (
                    (
                        admin_link(r),
                        r.status,
                        " manually edited" if r.is_manually_edited else "",
                    )
                    for r in revs
                ),
            ),
        )

    @admin.display(description="Published preview")
    def published_preview(self, obj: Lesson) -> SafeString:
        if obj.published_revision is None:
            return mark_safe("Nothing published yet.")  # noqa: S308
        return render_preview(obj.published_revision.payload)

    @admin.action(description="Generate content with the local LLM")
    def generate_content(self, request: HttpRequest, queryset: QuerySet[Lesson]) -> None:
        links = []
        for lesson in queryset:
            job = create_job(lesson)
            url = reverse("admin:authoring_generationjob_change", args=[job.pk])
            links.append(format_html('<a href="{}">job {} ({})</a>', url, job.pk, lesson.slug))
        if links:
            self.message_user(
                request,
                format_html(
                    "Queued generation: {}",
                    format_html_join(", ", "{}", ((link,) for link in links)),
                ),
                messages.SUCCESS,
            )


@admin.register(LessonRevision)
class LessonRevisionAdmin(ReadOnlyAdmin):
    list_display = (
        "lesson",
        "content_version",
        "status_display",
        "is_manually_edited",
        "imported_at",
    )
    list_filter = ("is_manually_edited", "lesson__unit__level")
    search_fields = ("lesson__slug", "lesson__title")
    actions = ["publish_version"]
    fields = (
        "lesson",
        "content_version",
        "content_hash",
        "source_path",
        "is_manually_edited",
        "content_import",
        "imported_at",
        "published_at",
        "status_display",
        "preview",
        "yaml_display",
    )
    readonly_fields = fields

    def get_queryset(self, request: HttpRequest) -> QuerySet[LessonRevision]:
        return super().get_queryset(request).select_related("lesson")

    @admin.display(description="Status")
    def status_display(self, obj: LessonRevision) -> str:
        return obj.status

    @admin.display(description="Preview")
    def preview(self, obj: LessonRevision) -> SafeString:
        return render_preview(obj.payload)

    @admin.display(description="YAML")
    def yaml_display(self, obj: LessonRevision) -> SafeString:
        return format_html("<pre>{}</pre>", dump_yaml(obj.payload))

    @admin.action(description="Publish this version (rollback/forward)")
    def publish_version(self, request: HttpRequest, queryset: QuerySet[LessonRevision]) -> None:
        if queryset.count() != 1:
            self.message_user(request, "Select exactly one revision to publish.", messages.ERROR)
            return
        revision = queryset.get()
        publish_revision(revision)
        self.message_user(request, f"Published {revision} as the live version.", messages.SUCCESS)


@admin.register(ContentImport)
class ContentImportAdmin(ReadOnlyAdmin):
    list_display = ("id", "started_at", "ok", "dry_run", "git_sha")
    list_filter = ("ok", "dry_run")
    fields = (
        "started_at",
        "finished_at",
        "dry_run",
        "ok",
        "git_sha",
        "summary_display",
        "issues_display",
    )
    readonly_fields = fields

    @admin.display(description="Summary")
    def summary_display(self, obj: ContentImport) -> SafeString:
        if not obj.summary:
            return mark_safe("-")  # noqa: S308
        return format_html(
            "<ul>{}</ul>",
            format_html_join(
                "",
                "<li><b>{}</b>: {}</li>",
                (
                    (k, ", ".join(v) if isinstance(v, list) and v else (v or "none"))
                    for k, v in obj.summary.items()
                ),
            ),
        )

    @admin.display(description="Issues")
    def issues_display(self, obj: ContentImport) -> SafeString:
        if not obj.issues:
            return mark_safe("No issues.")  # noqa: S308
        rows = []
        for i in obj.issues:
            if isinstance(i, dict):
                rows.append((i.get("severity", ""), i.get("path", ""), i.get("message", "")))
            else:
                rows.append(("", "", str(i)))
        return format_html(
            "<table><tr><th>Severity</th><th>Path</th><th>Message</th></tr>{}</table>",
            format_html_join("", "<tr><td>{}</td><td>{}</td><td>{}</td></tr>", rows),
        )


@admin.register(Unit)
class UnitAdmin(ReadOnlyAdmin):
    list_display = ("slug", "title", "level", "order")
    list_filter = ("level",)
    search_fields = ("slug", "title")


@admin.register(GrammarTopic)
class GrammarTopicAdmin(ReadOnlyAdmin):
    list_display = ("slug", "title", "level")
    list_filter = ("level",)
    search_fields = ("slug", "title")


@admin.register(Exercise)
class ExerciseAdmin(ReadOnlyAdmin):
    list_display = ("stable_id", "lesson", "kind")
    list_filter = ("kind",)
    search_fields = ("stable_id",)


@admin.register(ExerciseRevision)
class ExerciseRevisionAdmin(ReadOnlyAdmin):
    list_display = ("exercise", "lesson_revision", "origin")
    list_filter = ("origin",)
    search_fields = ("exercise__stable_id",)
    fields = ("exercise", "lesson_revision", "origin", "content_hash", "payload_display")
    readonly_fields = fields

    @admin.display(description="Payload")
    def payload_display(self, obj: ExerciseRevision) -> SafeString:
        return format_html("<pre>{}</pre>", dump_yaml(obj.payload))
