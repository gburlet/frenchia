from pathlib import Path

from contentkit.models import Lesson
from contentkit.reference import QuebecTerm, Reference
from contentkit.validate import Issue, check_lesson_quality, load_repository

from .factories import lesson_data, make_repo, write_lesson


def messages(issues: list[Issue]) -> list[str]:
    return [f"{i.severity}:{i.message}" for i in issues]


def test_valid_repository_has_no_errors(tmp_path: Path) -> None:
    repo = load_repository(make_repo(tmp_path))
    assert repo.errors == []
    assert list(repo.outlines) == ["a2-passe-compose-er", "a2-imparfait"]


def test_reference_integrity(tmp_path: Path) -> None:
    root = make_repo(tmp_path, lessons=[])
    write_lesson(root, lesson_data(id="a2-not-in-outline", grammar_topics=["nope"]))
    moved = lesson_data()
    moved["level"] = "B1"
    path = write_lesson(root, moved)
    path.rename(root / "lessons" / "b1" / "wrong-name.yaml")
    found = " | ".join(messages(load_repository(root).issues))
    assert "lesson is not in any curriculum outline" in found
    assert "unknown grammar topic 'nope'" in found
    assert "file name must be a2-passe-compose-er.yaml" in found
    assert "outline places this lesson in A2/a2-u01-past" in found


def test_schema_errors_are_reported_with_location(tmp_path: Path) -> None:
    root = make_repo(tmp_path, lessons=[])
    bad = lesson_data()
    bad["exercises"][0]["answers"] = []
    write_lesson(root, bad)
    issues = load_repository(root).errors
    assert any("exercises.0.fill_blank.answers" in i.path for i in issues)


def reference() -> Reference:
    ref = Reference(Path("."))
    ref.nouns = {"tuque": {"gender": "f", "freq": 1.0}, "livre": {"gender": "mf", "freq": 1.0}}
    ref.verbs = {
        "manger": {
            "participle_past": "mangé",
            "participle_present": "mangeant",
            "forms": {
                "indicatif.passe_compose": {"je": "ai mangé", "il": "a mangé"},
                "indicatif.present": {"je": "mange"},
            },
        },
        "aller": {
            "participle_past": "allé",
            "participle_present": "allant",
            "forms": {
                "indicatif.passe_compose": {
                    "je": "suis allé",
                    "il": "est allé",
                    "ils": "sont allés",
                }
            },
        },
    }
    ref.quebec = [
        QuebecTerm(
            term="magasiner",
            match=[r"\bmagasin"],
            meaning="shop",
            france="faire du shopping",
            formality="standard",
        )
    ]
    return ref


def test_quality_accepts_good_lesson() -> None:
    assert check_lesson_quality(Lesson.model_validate(lesson_data()), reference()) == []


def test_quality_catches_invalid_verb_forms_and_repeats() -> None:
    data = lesson_data()
    data["exercises"][0] |= {
        "sentence": "Elle ___ au dépanneur.",
        "answers": ["a allé"],
        "hint": "(aller)",
    }
    data["exercises"].append(
        {
            "type": "fill_blank",
            "id": "ex-04",
            "sentence": "Nous ___ allés au parc.",
            "answers": ["sommes allés"],
            "hint": "(aller)",
            "translation_en": "We went.",
        }
    )
    data["exercises"].append(
        {
            "type": "fill_blank",
            "id": "ex-05",
            "sentence": "Elles ___ au parc.",
            "answers": ["sont allées"],
            "hint": "aller",
            "translation_en": "They went.",
        }
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:'a allé' is not a form of 'aller' in the reference" in found
    assert any("word repeated" in m for m in found)
    assert not any("sont allées" in m for m in found)  # agreement is accepted


def test_quality_checks_gender_language_and_quebec_claims() -> None:
    data = lesson_data()
    data["sections"].append(
        {
            "type": "vocabulary",
            "id": "words",
            "heading": "Mots",
            "items": [
                {"fr": "tuque", "en": "winter hat", "pos": "noun", "gender": "m", "region": "qc"},
                {"fr": "livre", "en": "book/pound", "pos": "noun", "gender": "f"},
                {"fr": "bécosse", "en": "outhouse", "pos": "noun", "gender": "f", "region": "qc"},
            ],
        }
    )
    data["exercises"][1]["accepted_answers"] = ["We went shopping with the kids."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:'tuque' is f, not m (Lexique)" in found
    assert not any("'livre'" in m for m in found)  # both genders exist
    assert any("'bécosse' is not in the verified lexicon" in m for m in found)
    assert "error:en_fr answers must be French" in found


def test_leftover_latex_is_flagged() -> None:
    data = lesson_data()
    data["sections"][0]["body"] = "parler $\\rightarrow$ parlé"
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("LaTeX markup" in m for m in found)
