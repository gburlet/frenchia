from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from authoring.models import GenerationJob
from authoring.prompts import PROMPT_VERSIONS
from authoring.services import ReviewError, approve, create_job, reject, request_revision, run_job
from contentkit.tests.factories import make_repo
from curriculum.importer import import_content
from curriculum.models import Lesson

from .scripted import ScriptedChat

pytestmark = pytest.mark.django_db


@pytest.fixture
def root(settings: Any, tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "content", lessons=[])
    settings.CONTENT_DIR = root
    import_content(root)  # structure only: lesson slots exist, no content yet
    return root


@pytest.fixture(autouse=True)
def scripted_llm() -> Any:
    with patch("authoring.services.get_chat_model", return_value=ScriptedChat()):
        yield


def generated(root: Path) -> GenerationJob:
    job = create_job(Lesson.objects.get(slug="a2-passe-compose-er"), enqueue=False)
    return run_job(job.pk)


def test_run_job_writes_a_draft_for_review(root: Path) -> None:
    job = generated(root)
    assert job.status == GenerationJob.Status.NEEDS_REVIEW, job.error
    assert job.draft_path == f"drafts/a2/a2-passe-compose-er.job-{job.pk}.yaml"
    assert (root / job.draft_path).exists()
    assert job.output and job.output["content_version"] == 1
    assert job.llm_calls > 0 and job.prompts == PROMPT_VERSIONS
    assert job.progress[-1]["message"].startswith("Done")


def test_approve_promotes_imports_and_publishes(root: Path) -> None:
    job = generated(root)
    path = approve(job)
    assert (
        path == (root / "lessons" / "a2" / "a2-passe-compose-er.yaml").resolve() and path.exists()
    )
    assert not (root / f"drafts/a2/a2-passe-compose-er.job-{job.pk}.yaml").exists()
    lesson = Lesson.objects.get(slug="a2-passe-compose-er")
    assert lesson.published_revision is not None and lesson.published_revision.content_version == 1
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.APPROVED
    with pytest.raises(ReviewError, match="not awaiting review"):
        approve(job)
    # A second generation becomes v2; the v1 revision (and its exercises) stays.
    second = generated(root)
    assert second.output and second.output["content_version"] == 2
    approve(second)
    assert lesson.revisions.count() == 2


def test_validation_errors_block_approval_unless_overridden(root: Path) -> None:
    job = generated(root)
    job.validation = [{"severity": "error", "path": "x", "message": "bad"}]
    job.save()
    with pytest.raises(ReviewError, match="1 validation errors"):
        approve(job)
    approve(job, allow_errors=True)


def test_conflict_when_published_file_changed_since_generation(root: Path) -> None:
    job = generated(root)
    approve(generated(root))  # another draft got published in the meantime
    with pytest.raises(ReviewError, match="changed since this draft was generated"):
        approve(job)


def test_reject_discards_the_draft(root: Path) -> None:
    job = generated(root)
    draft = root / job.draft_path
    reject(job, "Too hard for A2")
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.REJECTED and not draft.exists()
    assert job.reviewer_notes == "Too hard for A2"


def test_request_revision_creates_child_job_on_the_draft(
    root: Path, django_capture_on_commit_callbacks: Callable[..., Any]
) -> None:
    job = generated(root)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        child = request_revision(job, "Add a Québec example", ["table"])
    assert len(callbacks) == 1  # enqueued for the worker
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.REJECTED and f"job {child.pk}" in job.reviewer_notes
    child = run_job(child.pk)
    assert child.status == GenerationJob.Status.NEEDS_REVIEW, child.error
    assert (
        child.output and child.output["content_version"] == 1
    )  # still the unpublished draft version
    table = next(s for s in child.output["sections"] if s["id"] == "table")
    assert table["heading"].endswith("(révisé)")
    approve(child)
    assert Lesson.objects.get(slug="a2-passe-compose-er").published_revision is not None


def test_failures_are_recorded(root: Path) -> None:
    job = create_job(Lesson.objects.get(slug="a2-passe-compose-er"), enqueue=False)
    with patch(
        "authoring.services.LessonGenerator.generate", side_effect=RuntimeError("LLM exploded")
    ):
        job = run_job(job.pk)
    assert job.status == GenerationJob.Status.FAILED and "LLM exploded" in job.error


def test_recover_jobs_requeues_interrupted_jobs(
    root: Path, django_capture_on_commit_callbacks: Callable[..., Any]
) -> None:
    from django.core.management import call_command

    job = create_job(Lesson.objects.get(slug="a2-passe-compose-er"), enqueue=False)
    GenerationJob.objects.filter(pk=job.pk).update(status=GenerationJob.Status.RUNNING)
    with django_capture_on_commit_callbacks(execute=False) as callbacks:
        call_command("recover_jobs")
    job.refresh_from_db()
    assert job.status == GenerationJob.Status.QUEUED and len(callbacks) == 1
    assert "Interrupted" in job.progress[-1]["message"]
    assert run_job(job.pk).status == GenerationJob.Status.NEEDS_REVIEW  # runs normally again


class DownChat(ScriptedChat):
    def complete(self, messages: Any, **kwargs: Any) -> Any:
        from inference.errors import InferenceUnavailable

        raise InferenceUnavailable("llm", "llm is unavailable (retrying shortly)")


def test_an_unavailable_llm_requeues_the_job_instead_of_failing_it(root: Path) -> None:
    job = create_job(Lesson.objects.get(slug="a2-passe-compose-er"), enqueue=False)
    with (
        patch("authoring.services.get_chat_model", return_value=DownChat()),
        patch("authoring.services._enqueue") as enqueue,
    ):
        for _ in range(7):
            job = run_job(job.pk)
    assert enqueue.call_count == 6  # six retries, then it fails
    assert "run_after" in enqueue.call_args.kwargs
    assert job.status == GenerationJob.Status.FAILED
    assert sum(p["message"].startswith("LLM unavailable") for p in job.progress) == 6
