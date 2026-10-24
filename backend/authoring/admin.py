import difflib
from typing import Any

from django.contrib import admin, messages
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils.html import format_html

from contentkit.yamlio import dump_yaml
from curriculum.admin import render_preview

from .forms import ApproveForm, RejectForm, RevisionForm
from .models import GenerationJob
from .services import ReviewError, approve, reject, request_revision

STATUS_COLORS = {
    "queued": "#888",
    "running": "#2563eb",
    "needs_review": "#d97706",
    "approved": "#16a34a",
    "rejected": "#777",
    "failed": "#dc2626",
}


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "lesson",
        "kind",
        "colored_status",
        "errors",
        "warnings",
        "created_at",
        "duration",
        "model",
    )
    list_filter = ("status", "kind")
    search_fields = ("lesson__slug", "lesson__title")
    list_select_related = ("lesson",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    @admin.display(description="Status", ordering="status")
    def colored_status(self, obj: GenerationJob) -> str:
        return format_html(
            '<b style="color:{}">{}</b>',
            STATUS_COLORS.get(obj.status, "inherit"),
            obj.get_status_display(),
        )

    @admin.display(description="Errors")
    def errors(self, obj: GenerationJob) -> int:
        return obj.error_count

    @admin.display(description="Warnings")
    def warnings(self, obj: GenerationJob) -> int:
        return sum(1 for i in obj.validation if i.get("severity") == "warning")

    @admin.display(description="Duration")
    def duration(self, obj: GenerationJob) -> str:
        if obj.started_at and obj.finished_at:
            return f"{(obj.finished_at - obj.started_at).total_seconds():.0f}s"
        return "-"

    # -- review screen ---------------------------------------------------------------------

    def get_urls(self) -> list[URLPattern]:
        def wrap(view: Any) -> Any:
            return self.admin_site.admin_view(view)

        custom = [
            path(
                f"<int:pk>/{name}/",
                wrap(getattr(self, f"{name}_view")),
                name=f"authoring_generationjob_{name}",
            )
            for name in ("approve", "reject", "revise")
        ]
        return [*custom, *super().get_urls()]

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        job = get_object_or_404(
            GenerationJob.objects.select_related("lesson__published_revision"), pk=object_id
        )
        if not self.has_view_or_change_permission(request, job):
            from django.core.exceptions import PermissionDenied

            raise PermissionDenied
        errors = [i for i in job.validation if i.get("severity") == "error"]
        others = [i for i in job.validation if i.get("severity") != "error"]
        published = job.lesson.published_revision
        diff = ""
        if job.output:
            old = dump_yaml(published.payload) if published else ""
            diff = "".join(
                difflib.unified_diff(
                    old.splitlines(keepends=True),
                    dump_yaml(job.output).splitlines(keepends=True),
                    fromfile=f"published v{published.content_version}" if published else "none",
                    tofile=f"draft job {job.pk}",
                )
            )
        reviewable = job.status == GenerationJob.Status.NEEDS_REVIEW
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Review job {job.pk}: {job.lesson_id}",
            "job": job,
            "issues": [*errors, *others],
            "error_count": len(errors),
            "preview": render_preview(job.output) if job.output else "",
            "diff": diff,
            "diff_lines": [(ln, _diff_class(ln)) for ln in diff.splitlines()],
            "is_new": published is None,
            "auto_refresh": job.status
            in (GenerationJob.Status.QUEUED, GenerationJob.Status.RUNNING),
            "reviewable": reviewable,
            "can_reject": reviewable or job.status == GenerationJob.Status.FAILED,
            "status_color": STATUS_COLORS.get(job.status, "inherit"),
            "parent_url": reverse("admin:authoring_generationjob_change", args=[job.parent_id])
            if job.parent_id
            else "",
            **(extra_context or {}),
        }
        return TemplateResponse(request, "authoring/admin/review.html", context)

    def _job_redirect(self, job_id: int) -> HttpResponseRedirect:
        return HttpResponseRedirect(reverse("admin:authoring_generationjob_change", args=[job_id]))

    def _post_job(self, request: HttpRequest, pk: int) -> GenerationJob | None:
        job = get_object_or_404(GenerationJob, pk=pk)
        if request.method != "POST":
            return None
        return job

    def approve_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        job = self._post_job(request, pk)
        if job is None:
            return self._job_redirect(pk)
        form = ApproveForm(request.POST)
        form.is_valid()
        try:
            target = approve(
                job,
                allow_errors=form.cleaned_data.get("allow_errors", False),
                allow_overwrite_edits=form.cleaned_data.get("allow_overwrite_edits", False),
            )
        except ReviewError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            self.message_user(request, f"Approved and published ({target.name}).", messages.SUCCESS)
        return self._job_redirect(pk)

    def reject_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        job = self._post_job(request, pk)
        if job is None:
            return self._job_redirect(pk)
        form = RejectForm(request.POST)
        form.is_valid()
        try:
            reject(job, form.cleaned_data.get("notes", ""))
        except ReviewError as exc:
            self.message_user(request, str(exc), messages.ERROR)
        else:
            self.message_user(request, "Draft rejected.", messages.SUCCESS)
        return self._job_redirect(pk)

    def revise_view(self, request: HttpRequest, pk: int) -> HttpResponse:
        job = self._post_job(request, pk)
        if job is None:
            return self._job_redirect(pk)
        form = RevisionForm(request.POST)
        if not form.is_valid():
            self.message_user(request, "Describe what should change.", messages.ERROR)
            return self._job_redirect(pk)
        try:
            child = request_revision(job, form.cleaned_data["notes"], form.cleaned_data["targets"])
        except ReviewError as exc:
            self.message_user(request, str(exc), messages.ERROR)
            return self._job_redirect(pk)
        self.message_user(request, f"Revision requested: job {child.pk} queued.", messages.SUCCESS)
        return self._job_redirect(child.pk)


def _diff_class(line: str) -> str:
    if line.startswith(("+++", "---")):
        return "hdr"
    if line.startswith("+"):
        return "add"
    if line.startswith("-"):
        return "del"
    if line.startswith("@@"):
        return "hunk"
    return ""
