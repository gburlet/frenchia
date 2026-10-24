import pytest
from pydantic import ValidationError

from contentkit.models import Lesson
from contentkit.yamlio import content_hash, dump_yaml, to_data

from .factories import lesson_data


def test_valid_lesson_round_trips_through_yaml() -> None:
    import yaml

    lesson = Lesson.model_validate(lesson_data())
    text = dump_yaml(to_data(lesson))
    assert "body: |" in text  # multi-line prose as a block scalar
    assert Lesson.model_validate(yaml.safe_load(text)) == lesson


@pytest.mark.parametrize(
    ("patch", "message"),
    [
        ({"sentence": "Hier, j'ai mangé."}, "exactly one ___"),
        ({"sentence": "___ et ___"}, "exactly one ___"),
    ],
)
def test_fill_blank_needs_one_blank(patch: dict[str, str], message: str) -> None:
    data = lesson_data()
    data["exercises"][0] |= patch
    with pytest.raises(ValidationError, match=message):
        Lesson.model_validate(data)


def test_comprehension_must_reference_a_reading() -> None:
    data = lesson_data()
    data["exercises"][2]["reading_id"] = "nope"
    with pytest.raises(ValidationError, match="unknown reading"):
        Lesson.model_validate(data)


def test_duplicate_ids_and_answers_rejected() -> None:
    data = lesson_data()
    data["exercises"][1]["id"] = "ex-01"
    with pytest.raises(ValidationError, match="duplicate exercise ids"):
        Lesson.model_validate(data)
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["On a magasiné.", "on a magasiné."]
    with pytest.raises(ValidationError, match="duplicate accepted answers"):
        Lesson.model_validate(data)


def test_answer_index_in_range_and_nouns_need_gender() -> None:
    data = lesson_data()
    data["exercises"][2]["answer_index"] = 5
    with pytest.raises(ValidationError, match="out of range"):
        Lesson.model_validate(data)
    data = lesson_data()
    data["sections"].append(
        {
            "type": "vocabulary",
            "id": "words",
            "heading": "Mots",
            "items": [
                {"fr": "tuque", "en": "hat", "pos": "noun"},
                {"fr": "a", "en": "a", "pos": "other"},
                {"fr": "b", "en": "b", "pos": "other"},
            ],
        }
    )
    with pytest.raises(ValidationError, match="needs a gender"):
        Lesson.model_validate(data)


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        Lesson.model_validate(lesson_data(surprise=True))


def test_hash_ignores_version_and_provenance_but_not_content() -> None:
    base = Lesson.model_validate(lesson_data())
    bumped = Lesson.model_validate(
        lesson_data(
            content_version=7,
            provenance={
                "generator": "ollama/x",
                "generated_at": "2026-10-24T12:00:00Z",
                "generated_hash": "abc",
            },
        )
    )
    edited = Lesson.model_validate(lesson_data(title="Autre titre"))
    assert content_hash(base) == content_hash(bumped)
    assert content_hash(base) != content_hash(edited)
