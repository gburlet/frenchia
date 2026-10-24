from pathlib import Path
from typing import Any

import pytest
from django.test import Client
from django.urls import reverse

from authoring.models import GenerationJob
from contentkit.tests.factories import lesson_data, make_repo
from curriculum.importer import import_content
from curriculum.models import Lesson, LessonRevision

pytestmark = pytest.mark.django_db


@pytest.fixture
def repo(settings: Any, tmp_path: Path) -> Path:
    root = tmp_path / "content"
    make_repo(root, lessons=[])
    settings.CONTENT_DIR = root
    import_content(root)  # structure only
    return root


def make_job(validation: list[dict[str, str]] | None = None, **kw: Any) -> GenerationJob:
    return GenerationJob.objects.create(
        lesson=Lesson.objects.get(pk="a2-passe-compose-er"),
        status=GenerationJob.Status.NEEDS_REVIEW,
        output=lesson_data(),
        validation=validation or [],
        prompts={"system": "v1"},
        **kw,
    )


def post(client: Client, name: str, job: GenerationJob, data: dict[str, str] | None = None) -> Any:
    return client.post(
        reverse(f"admin:authoring_generationjob_{name}", args=[job.pk]), data or {}, follow=True
    )


def test_review_page_renders(admin_client: Client, repo: Path) -> None:
    job = make_job(
        [
            {"severity": "warning", "path": "sections[0]", "message": "a warning"},
            {"severity": "error", "path": "exercises[0]", "message": "an error"},
        ]
    )
    resp = admin_client.get(reverse("admin:authoring_generationjob_change", args=[job.pk]))
    assert resp.status_code == 200
    html = resp.content.decode()
    assert "Le passé composé des verbes" in html  # preview
    assert "an error" in html and "a warning" in html
    assert html.index("an error") < html.index("a warning")
    assert "New lesson" in html
    assert "disabled" in html
    assert 'http-equiv="refresh"' not in html


def test_review_page_diff_and_refresh(admin_client: Client, repo: Path) -> None:
    lesson = Lesson.objects.get(pk="a2-passe-compose-er")
    rev = LessonRevision.objects.create(
        lesson=lesson,
        content_version=1,
        content_hash="h" * 64,
        payload=lesson_data(title="Ancien titre"),
        source_path="p",
    )
    lesson.published_revision = rev
    lesson.save()
    job = make_job()
    html = admin_client.get(
        reverse("admin:authoring_generationjob_change", args=[job.pk])
    ).content.decode()
    assert "-title: Ancien titre" in html
    queued = GenerationJob.objects.create(lesson=lesson)
    html = admin_client.get(
        reverse("admin:authoring_generationjob_change", args=[queued.pk])
    ).content.decode()
    assert 'http-equiv="refresh"' in html


def test_job_list(admin_client: Client, repo: Path) -> None:
    make_job()
    assert admin_client.get(reverse("admin:authoring_generationjob_changelist")).status_code == 200
    assert admin_client.get(reverse("admin:authoring_generationjob_add")).status_code == 403


def test_approve_publishes(admin_client: Client, repo: Path) -> None:
    job = make_job()
    post(admin_client, "approve", job)
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.APPROVED
    lesson = Lesson.objects.get(pk="a2-passe-compose-er")
    assert lesson.published_revision is not None
    assert LessonRevision.objects.filter(lesson=lesson).count() == 1


def test_approve_blocked_by_errors(admin_client: Client, repo: Path) -> None:
    job = make_job([{"severity": "error", "path": "x", "message": "bad"}])
    resp = post(admin_client, "approve", job)
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.NEEDS_REVIEW
    assert "validation errors" in resp.content.decode()
    assert not LessonRevision.objects.exists()


def test_reject(admin_client: Client, repo: Path) -> None:
    job = make_job()
    post(admin_client, "reject", job, {"notes": "too easy"})
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.REJECTED
    assert job.reviewer_notes == "too easy"


def test_request_revision_creates_child(
    admin_client: Client, repo: Path, django_capture_on_commit_callbacks: Any
) -> None:
    job = make_job()
    with django_capture_on_commit_callbacks(execute=False):
        resp = post(
            admin_client, "revise", job, {"notes": "more examples", "targets": "intro, ex-01"}
        )
    child = GenerationJob.objects.get(parent=job)
    assert child.kind == GenerationJob.Kind.REVISION
    assert child.targets == ["intro", "ex-01"]
    assert resp.redirect_chain[-1][0] == reverse(
        "admin:authoring_generationjob_change", args=[child.pk]
    )


def test_request_revision_requires_notes(admin_client: Client, repo: Path) -> None:
    job = make_job()
    post(admin_client, "revise", job, {"notes": " "})
    assert not GenerationJob.objects.filter(parent=job).exists()
