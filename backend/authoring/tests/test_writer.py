from datetime import UTC, datetime
from pathlib import Path

import pytest

from authoring.writer import ContentWriter, WriteConflict
from contentkit.models import Lesson, Provenance
from contentkit.tests.factories import lesson_data, make_repo, write_lesson
from contentkit.yamlio import content_hash


def test_drafts_are_confined_to_the_content_root(tmp_path: Path) -> None:
    writer = ContentWriter(tmp_path)
    lesson = Lesson.model_validate(lesson_data())
    path = writer.write_draft(lesson, job_id=4)
    assert path == (tmp_path / "drafts" / "a2" / "a2-passe-compose-er.job-4.yaml").resolve()
    with pytest.raises(ValueError, match="outside the content root"):
        writer._confined(tmp_path / ".." / "escape.yaml")


def test_promote_detects_conflicts_and_manual_edits(tmp_path: Path) -> None:
    root = make_repo(tmp_path, lessons=[])
    writer = ContentWriter(root)
    new = Lesson.model_validate(lesson_data(content_version=2))
    # Published file changed after the job captured base_hash "" (no file).
    generated = Lesson.model_validate(lesson_data())
    stamped = generated.model_copy(
        update={
            "provenance": Provenance(
                generator="llm/x",
                generated_at=datetime(2026, 10, 24, tzinfo=UTC),
                generated_hash=content_hash(generated),
            )
        }
    )
    write_lesson(root, stamped.model_dump(mode="json", exclude_none=True))
    with pytest.raises(WriteConflict, match="changed since"):
        writer.promote(new, base_hash="")
    assert writer.promote(new, base_hash=content_hash(generated)).exists()
    # A manual edit (hash differs from generated_hash) blocks fresh generations by default.
    edited = stamped.model_copy(update={"title": "Titre retouché à la main"})
    write_lesson(root, edited.model_dump(mode="json", exclude_none=True))
    with pytest.raises(WriteConflict, match="manual edits"):
        writer.promote(new, base_hash=content_hash(edited))
    writer.promote(new, base_hash=content_hash(edited), allow_overwrite_edits=True)
    assert writer.read_lesson(writer.lesson_path(new)) == new
