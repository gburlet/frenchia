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
    make_repo(root)
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    return root


def test_lesson_changelist_and_detail(admin_client: Client, repo: Path) -> None:
    resp = admin_client.get(reverse("admin:curriculum_lesson_changelist"))
    assert resp.status_code == 200
    assert b"a2-passe-compose-er" in resp.content
    resp = admin_client.get(reverse("admin:curriculum_lesson_change", args=["a2-passe-compose-er"]))
    assert resp.status_code == 200
    assert "Le passé composé".encode() in resp.content
    assert b"Hier, j&#x27;___ une poutine." in resp.content


def test_generate_action_creates_jobs(
    admin_client: Client, repo: Path, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=False):
        resp = admin_client.post(
            reverse("admin:curriculum_lesson_changelist"),
            {
                "action": "generate_content",
                "_selected_action": ["a2-passe-compose-er", "a2-imparfait"],
            },
            follow=True,
        )
    assert resp.status_code == 200
    assert GenerationJob.objects.count() == 2
    assert b"Queued generation" in resp.content


def test_revision_view_and_publish_action(admin_client: Client, repo: Path) -> None:
    lesson = Lesson.objects.get(pk="a2-passe-compose-er")
    first = lesson.revisions.get()
    v2 = LessonRevision.objects.create(
        lesson=lesson,
        content_version=2,
        content_hash="x" * 64,
        payload=lesson_data(content_version=2),
        source_path="p",
    )
    resp = admin_client.get(reverse("admin:curriculum_lessonrevision_change", args=[v2.pk]))
    assert resp.status_code == 200
    assert b"content_version: 2" in resp.content

    url = reverse("admin:curriculum_lessonrevision_changelist")
    admin_client.post(url, {"action": "publish_version", "_selected_action": [v2.pk]})
    lesson.refresh_from_db()
    assert lesson.published_revision_id == v2.pk
    # rollback
    admin_client.post(url, {"action": "publish_version", "_selected_action": [first.pk]})
    lesson.refresh_from_db()
    assert lesson.published_revision_id == first.pk


def test_readonly_models_have_no_add(admin_client: Client, repo: Path) -> None:
    for name in ("unit", "grammartopic", "exercise", "exerciseRevision", "contentimport"):
        url = reverse(f"admin:curriculum_{name.lower()}_changelist")
        resp = admin_client.get(url)
        assert resp.status_code == 200
        assert admin_client.get(url + "add/").status_code == 403
    record = import_content(repo).record
    assert record is not None
    resp = admin_client.get(reverse("admin:curriculum_contentimport_change", args=[record.pk]))
    assert resp.status_code == 200
