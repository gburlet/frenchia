import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import Client

from authoring.external_review import REVIEW_DIR, revision_notes
from authoring.models import GenerationJob
from authoring.services import create_job, run_job
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import Lesson

from .scripted import ScriptedChat

pytestmark = pytest.mark.django_db

FINDINGS = {
    "issues": [
        {
            "item_id": "ex-01",
            "severity": "error",
            "category": "grammar",
            "problem": "Missing preposition.",
            "suggested_fix": "Use « parler à ».",
        },
        {
            "item_id": "table",
            "severity": "suggestion",
            "category": "consistency",
            "problem": "On row shows only il.",
            "suggested_fix": "Add « on a mangé ».",
        },
        {
            "item_id": "nope",
            "severity": "suggestion",
            "category": "other",
            "problem": "Mystery.",
            "suggested_fix": "?",
        },
    ]
}


@pytest.fixture
def job(settings: Any, tmp_path: Path) -> GenerationJob:
    root = make_repo(tmp_path / "content", lessons=[])
    settings.CONTENT_DIR = root
    import_content(root)
    with patch("authoring.services.get_authoring_chat_model", return_value=ScriptedChat()):
        job = create_job(Lesson.objects.get(slug="a2-passe-compose-er"), enqueue=False)
        return run_job(job.pk)


def test_export_writes_a_self_contained_prompt(job: GenerationJob, settings: Any) -> None:
    call_command("content_review_export")
    prompt = (Path(settings.CONTENT_DIR) / REVIEW_DIR / f"job-{job.pk}.prompt.txt").read_text()
    assert "Québec French (CEFR A2)" in prompt and '"id": "a2-passe-compose-er"' in prompt
    assert '"provenance"' not in prompt and '"issues"' in prompt  # lesson only, plus the schema


def test_import_attaches_findings_and_can_queue_a_revision(
    job: GenerationJob, settings: Any, django_capture_on_commit_callbacks: Any
) -> None:
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    call_command("content_review_export")
    (folder / f"job-{job.pk}.findings.json").write_text(json.dumps(FINDINGS))
    with django_capture_on_commit_callbacks(execute=False):
        call_command("content_review_import", reviewer="claude-haiku-5-5", revise=True)
    job.refresh_from_db()
    assert job.external_reviewer.startswith("claude-haiku-5-5")
    assert [f["unknown_item"] for f in job.external_review] == [False, False, True]
    assert not list(folder.glob(f"job-{job.pk}.*"))  # consumed
    child = GenerationJob.objects.get(parent=job)
    assert child.targets == ["ex-01"] and "parler à" in child.notes  # errors only
    assert job.status == GenerationJob.Status.REJECTED  # superseded by the revision


def test_approve_clean_publishes_a_draft_with_only_suggestions(
    job: GenerationJob, settings: Any
) -> None:
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    call_command("content_review_export")
    suggestions = {"issues": [i for i in FINDINGS["issues"] if i["severity"] == "suggestion"]}
    (folder / f"job-{job.pk}.findings.json").write_text(json.dumps(suggestions))
    call_command(
        "content_review_import", reviewer="claude-haiku-5-5", revise=True, approve_clean=True
    )
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.APPROVED
    assert not GenerationJob.objects.filter(parent=job).exists()
    assert Lesson.objects.get(slug="a2-passe-compose-er").published_revision is not None


def test_revisions_stop_after_max_rounds(
    job: GenerationJob, settings: Any, django_capture_on_commit_callbacks: Any
) -> None:
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    call_command("content_review_export")
    (folder / f"job-{job.pk}.findings.json").write_text(json.dumps(FINDINGS))
    with django_capture_on_commit_callbacks(execute=False):
        call_command(
            "content_review_import",
            reviewer="claude-haiku-5-5",
            revise=True,
            approve_clean=True,
            max_rounds=1,
        )
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.APPROVED  # out of rounds: published as it is
    assert not GenerationJob.objects.filter(parent=job).exists()


def test_invalid_findings_are_reported_not_imported(job: GenerationJob, settings: Any) -> None:
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"job-{job.pk}.findings.json").write_text('{"issues": [{"item_id": "x"}]}')
    with pytest.raises(Exception, match="not imported"):
        call_command("content_review_import", reviewer="claude-haiku-5-5")
    job.refresh_from_db()
    assert job.external_reviewed_at is None


def test_review_page_shows_findings_and_prefills_revision(
    job: GenerationJob, admin_client: Client
) -> None:
    job.external_review = [{**f, "unknown_item": False} for f in FINDINGS["issues"][:2]]
    job.external_reviewer = "claude-haiku-5-5 (prompt v1)"
    from django.utils import timezone

    job.external_reviewed_at = timezone.now()
    job.save()
    html = admin_client.get(f"/admin/authoring/generationjob/{job.pk}/change/").content.decode()
    assert "External review" in html and "Missing preposition." in html
    assert 'value="ex-01, table"' in html
    notes, _ = revision_notes(job)
    assert "ex-01 (error): Missing preposition." in notes


def test_unverified_quebec_claims_block_approval_and_go_to_the_reviser(
    job: GenerationJob, settings: Any, django_capture_on_commit_callbacks: Any
) -> None:
    job.validation = [
        {
            "severity": "warning",
            "path": "a2-passe-compose-er:vocabulary",
            "message": "Québec usage 'C'est de la roche' is not in the verified lexicon; check it",
        }
    ]
    job.save()
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    call_command("content_review_export")
    (folder / f"job-{job.pk}.findings.json").write_text('{"issues": []}')
    with django_capture_on_commit_callbacks(execute=False):
        call_command(
            "content_review_import", reviewer="claude-haiku-5-5", revise=True, approve_clean=True
        )
    child = GenerationJob.objects.get(parent=job)
    assert child.targets == ["vocabulary"] and "C'est de la roche" in child.notes
    assert not Lesson.objects.get(slug="a2-passe-compose-er").published_revision


def test_critic_flags_are_listed_for_the_reviewer_not_blocking(
    job: GenerationJob, settings: Any
) -> None:
    job.validation = [
        {
            "severity": "warning",
            "path": "a2-passe-compose-er:ex-01",
            "message": "AI critic on 'Je les ai finis.': 'finis': no agreement here",
        }
    ]
    job.save()
    call_command("content_review_export")
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    prompt = (folder / f"job-{job.pk}.prompt.txt").read_text()
    assert "often wrong" in prompt and "- ex-01: AI critic on 'Je les ai finis.'" in prompt
    (folder / f"job-{job.pk}.findings.json").write_text('{"issues": []}')
    call_command("content_review_import", reviewer="claude-haiku-5-5", approve_clean=True)
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.APPROVED


def test_validation_errors_alone_queue_a_revision(
    job: GenerationJob, settings: Any, django_capture_on_commit_callbacks: Any
) -> None:
    job.validation = [
        {"severity": "error", "path": "a2-passe-compose-er:ex-02.hint", "message": "too long"}
    ]
    job.save()
    folder = Path(settings.CONTENT_DIR) / REVIEW_DIR
    call_command("content_review_export")
    (folder / f"job-{job.pk}.findings.json").write_text('{"issues": []}')
    with django_capture_on_commit_callbacks(execute=False):
        call_command(
            "content_review_import", reviewer="claude-haiku-5-5", revise=True, approve_clean=True
        )
    child = GenerationJob.objects.get(parent=job)
    assert child.targets == ["ex-02"] and "ex-02.hint: too long" in child.notes


def test_published_lessons_can_be_proof_read_and_revised(
    settings: Any, tmp_path: Path, django_capture_on_commit_callbacks: Any
) -> None:
    root = make_repo(tmp_path / "pub")
    settings.CONTENT_DIR = root
    import_content(root, publish=True)
    folder = root / REVIEW_DIR
    call_command("content_review_export", published=[])
    prompt = folder / "lesson-a2-passe-compose-er.prompt.txt"
    assert '"id": "a2-passe-compose-er"' in prompt.read_text()
    (folder / "lesson-a2-passe-compose-er.findings.json").write_text(json.dumps(FINDINGS))
    with django_capture_on_commit_callbacks(execute=False):
        call_command("content_review_import", reviewer="claude-sonnet-5-5")
    job = GenerationJob.objects.get(lesson="a2-passe-compose-er")
    assert job.kind == "revision" and "parler à" in job.notes and "claude-sonnet" in job.notes
    assert not list(folder.glob("lesson-*"))
    # A lesson with a job in progress is not exported again.
    call_command("content_review_export", published=[])
    assert not list(folder.glob("lesson-*"))
