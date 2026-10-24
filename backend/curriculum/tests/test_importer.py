from pathlib import Path

import pytest

from contentkit.tests.factories import lesson_data, make_repo, write_lesson
from curriculum.importer import import_content, publish_revision
from curriculum.models import Exercise, ExerciseRevision, GrammarTopic, Lesson, LessonRevision, Unit

pytestmark = pytest.mark.django_db


def test_import_creates_structure_and_revisions(tmp_path: Path) -> None:
    result = import_content(make_repo(tmp_path))
    assert result.created == ["a2-passe-compose-er v1"] and not result.refused
    assert Unit.objects.get().slug == "a2-u01-past"
    assert set(GrammarTopic.objects.values_list("slug", flat=True)) == {
        "passe-compose-avoir",
        "imparfait",
    }
    lessons = list(Lesson.objects.values_list("slug", "order"))
    assert lessons == [("a2-passe-compose-er", 1), ("a2-imparfait", 2)]
    assert Exercise.objects.count() == 3 and ExerciseRevision.objects.count() == 3
    assert (
        Lesson.objects.get(slug="a2-passe-compose-er").published_revision is None
    )  # not published by default
    assert result.record is not None and result.record.ok


def test_reimport_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    import_content(root, publish=True)
    again = import_content(root, publish=True)
    assert (
        again.created == []
        and again.unchanged == ["a2-passe-compose-er v1"]
        and again.published == []
    )
    assert LessonRevision.objects.count() == 1


def test_changed_content_needs_a_version_bump(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    import_content(root)
    write_lesson(root, lesson_data(title="Nouveau titre"))
    refused = import_content(root)
    assert refused.refused and "without bumping content_version" in refused.refused[0]
    write_lesson(root, lesson_data(title="Nouveau titre", content_version=3))
    assert import_content(root).created == ["a2-passe-compose-er v3"]
    write_lesson(root, lesson_data(title="Entre-deux", content_version=2))
    assert "older than imported v3" in import_content(root).refused[0]


def test_new_version_keeps_old_exercise_revisions_and_rollback_moves_pointer(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    import_content(root, publish=True)
    v1 = LessonRevision.objects.get(content_version=1)
    data = lesson_data(content_version=2)
    data["exercises"][0]["answers"] = ["ai dévoré"]
    write_lesson(root, data)
    import_content(root, publish=True)
    exercise = Exercise.objects.get(stable_id="a2-passe-compose-er/ex-01")
    assert exercise.revisions.count() == 2  # history preserved, not overwritten
    lesson = Lesson.objects.get(slug="a2-passe-compose-er")
    assert lesson.published_revision is not None and lesson.published_revision.content_version == 2
    publish_revision(v1)
    lesson.refresh_from_db()
    assert lesson.published_revision == v1
    assert LessonRevision.objects.get(content_version=2).status == "superseded"


def test_revisions_are_immutable(tmp_path: Path) -> None:
    import_content(make_repo(tmp_path))
    revision = ExerciseRevision.objects.first()
    assert revision is not None
    revision.payload = {"tampered": True}
    with pytest.raises(ValueError, match="immutable"):
        revision.save()


def test_dry_run_persists_nothing_and_invalid_files_are_refused(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    result = import_content(root, dry_run=True)
    assert result.created and not LessonRevision.objects.exists() and not Unit.objects.exists()
    broken = lesson_data(id="a2-imparfait", title="")
    write_lesson(root, broken)
    result = import_content(root)
    assert any("a2-imparfait.yaml: invalid file" in r for r in result.refused)
    assert result.created == ["a2-passe-compose-er v1"]  # other lessons still import
