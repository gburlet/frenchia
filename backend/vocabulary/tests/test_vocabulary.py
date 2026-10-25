from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from django.test import Client
from django.utils import timezone

from accounts.models import LearnerProfile, User
from contentkit.tests.factories import lesson_data, make_repo
from contentkit.yamlio import dump_yaml
from curriculum.importer import import_content
from vocabulary.models import Lexeme, VocabCard, VocabReview, VocabSet
from vocabulary.services import check_recall, display

pytestmark = pytest.mark.django_db

THEMES = {
    "schema_version": 1,
    "themes": [
        {
            "id": "a2-vetements",
            "level": "A2",
            "title": "Les vêtements",
            "title_en": "Clothing",
            "scope": "Clothes.",
        }
    ],
}


def entry(entry_id: str, fr: str, gender: str | None, en: str, **extra: Any) -> dict[str, Any]:
    data = {
        "id": entry_id,
        "fr": fr,
        "en": en,
        "pos": "noun" if gender else "verb",
        "example_fr": f"J'aime {fr}.",
        "example_en": f"I like {en}.",
        **extra,
    }
    if gender:
        data["gender"] = gender
    return data


def vocab_set(version: int = 1, entries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": "a2-vetements",
        "content_version": version,
        "level": "A2",
        "title": "Les vêtements",
        "title_en": "Clothing",
        "entries": entries
        or [
            entry("tuque", "tuque", "f", "winter hat", region="qc"),
            entry("chandail", "chandail", "m", "sweater", region="qc"),
            entry("manteau", "manteau", "m", "coat"),
            entry("habit", "habit", "m", "suit"),
            entry("hockey", "hockey", "m", "hockey"),
            entry("habiller", "s'habiller", None, "to get dressed"),
        ],
    }


def lesson_with_vocab() -> dict[str, Any]:
    data = lesson_data()
    data["sections"].append(
        {
            "type": "vocabulary",
            "id": "words",
            "heading": "Mots",
            "items": [
                {"fr": "dépanneur", "en": "convenience store", "pos": "noun", "gender": "m"},
                {"fr": "magasiner", "en": "to shop", "pos": "verb", "region": "qc"},
                {"fr": "manteau", "en": "coat", "pos": "noun", "gender": "m"},
            ],
        }
    )
    return data


@pytest.fixture
def repo(settings: Any, tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "content", [lesson_with_vocab()])
    (root / "vocabulary" / "sets").mkdir(parents=True)
    (root / "vocabulary" / "themes.yaml").write_text(dump_yaml(THEMES))
    write_set(root, vocab_set())
    settings.CONTENT_DIR = root
    return root


def write_set(root: Path, data: dict[str, Any]) -> None:
    (root / "vocabulary" / "sets" / "a2-vetements.yaml").write_text(dump_yaml(data))


@pytest.fixture
def learner(client: Client) -> tuple[Client, User]:
    user = User.objects.create_user("marie", password="pw-123456789")
    client.force_login(user)
    return client, user


def test_import_creates_theme_and_lesson_sets(repo: Path) -> None:
    result = import_content(repo, publish=True)
    assert "vocabulary:a2-vetements v1" in result.created
    theme = VocabSet.objects.get(slug="a2-vetements")
    assert theme.lexemes.count() == 6 and theme.kind == "theme"
    lesson_set = VocabSet.objects.get(slug="lesson-a2-passe-compose-er")
    assert [lx.fr for lx in lesson_set.lexemes.all()] == ["dépanneur", "magasiner", "manteau"]
    assert import_content(repo).unchanged[-1] == "vocabulary:a2-vetements v1"


def test_changed_set_needs_a_version_bump_and_retires_dropped_words(repo: Path) -> None:
    import_content(repo, publish=True)
    smaller = vocab_set(entries=vocab_set()["entries"][1:])
    write_set(repo, smaller)
    assert any("bumping" in r for r in import_content(repo).refused)
    write_set(repo, {**smaller, "content_version": 2})
    import_content(repo)
    tuque = Lexeme.objects.get(stable_id="a2-vetements/tuque")
    assert tuque.retired and VocabSet.objects.get(slug="a2-vetements").content_version == 2


def test_display_articles() -> None:
    def lexeme(fr: str, gender: str) -> Lexeme:
        return Lexeme(fr=fr, gender=gender, pos="noun")

    assert display(lexeme("tuque", "f")) == "la tuque"
    assert display(lexeme("arbre", "m")) == "l'arbre"
    assert display(lexeme("hiver", "m")) == "l'hiver"
    assert display(lexeme("hockey", "m")) == "le hockey"


@pytest.mark.parametrize(
    ("answer", "result", "rating"),
    [
        ("une tuque", "correct", 3),
        ("La tuque.", "correct", 3),
        ("le tuque", "gender", 1),
        ("tuque", "article", 2),
        ("la tûque", "accent", 2),
        ("le bonnet", "incorrect", 1),
    ],
)
def test_recall_check_for_nouns(answer: str, result: str, rating: int) -> None:
    check = check_recall(Lexeme(fr="tuque", gender="f", pos="noun"), answer)
    assert (check["result"], check["suggested_rating"], check["expected"]) == (
        result,
        rating,
        "la tuque",
    )


def test_recall_check_for_reflexive_verbs() -> None:
    verb = Lexeme(fr="s'habiller", pos="verb")
    assert check_recall(verb, "s'habiller")["result"] == "correct"
    assert check_recall(verb, "habiller")["result"] == "article"


def test_learn_set_creates_both_directions_and_skips_known_words(
    repo: Path, learner: tuple[Client, User]
) -> None:
    client, user = learner
    import_content(repo, publish=True)
    assert client.post("/api/vocab/sets/a2-vetements/learn").json() == {
        "added": 6,
        "skipped": 0,
    }
    body = client.post("/api/vocab/sets/lesson-a2-passe-compose-er/learn").json()
    assert body == {"added": 2, "skipped": 1}  # manteau is already in the deck
    assert VocabCard.objects.filter(user=user).count() == 16


def test_queue_limits_new_cards_and_gates_recall(repo: Path, learner: tuple[Client, User]) -> None:
    client, user = learner
    import_content(repo, publish=True)
    profile = LearnerProfile.for_user(user)
    profile.daily_new_cards = 3
    profile.save()
    client.post("/api/vocab/sets/a2-vetements/learn")
    body = client.get("/api/vocab/review").json()
    assert body["new_remaining_today"] == 3
    cards = body["cards"]
    assert [c["direction"] for c in cards] == ["recognize"] * 3
    assert cards[0]["lexeme"]["display"] == "la tuque"
    previews = cards[0]["previews"]
    assert previews["1"] < previews["3"] < previews["4"]

    first = cards[0]["id"]
    client.post(f"/api/vocab/cards/{first}/review", {"rating": 3}, content_type="application/json")
    after = client.get("/api/vocab/review").json()
    assert after["new_remaining_today"] == 2
    # the recall card of "tuque" is unlocked once its recognition card has been seen
    assert "recall" in [c["direction"] for c in after["cards"]]


def test_review_schedules_and_records(repo: Path, learner: tuple[Client, User]) -> None:
    client, user = learner
    import_content(repo, publish=True)
    client.post("/api/vocab/sets/a2-vetements/learn")
    card = VocabCard.objects.filter(user=user, direction="recall").first()
    assert card is not None
    check = client.post(
        f"/api/vocab/cards/{card.pk}/check", {"answer": "le tuque"}, content_type="application/json"
    ).json()
    assert check["result"] in ("gender", "incorrect", "correct", "article", "accent")
    body = client.post(
        f"/api/vocab/cards/{card.pk}/review",
        {"rating": 4, "duration_ms": 3000, "answer": "x", "check_result": check["result"]},
        content_type="application/json",
    ).json()
    card.refresh_from_db()
    assert card.reps == 1 and card.due > timezone.now() + timedelta(days=1)
    assert body["interval_seconds"] > 86400
    review = VocabReview.objects.get(card=card)
    assert review.was_new and review.rating == 4

    stats = client.get("/api/vocab/sets").json()["stats"]
    assert stats["reviews_today"] == 1 and stats["words"] == 6
    slugs = [s["slug"] for s in client.get("/api/vocab/sets").json()["sets"]]
    assert slugs == ["a2-vetements", "lesson-a2-passe-compose-er"]  # themes first
    other = User.objects.create_user("autre", password="pw-123456789")
    client.force_login(other)
    assert client.post(f"/api/vocab/cards/{card.pk}/review", {"rating": 3}).status_code == 404


def test_set_detail_reports_word_status(repo: Path, learner: tuple[Client, User]) -> None:
    client, _ = learner
    import_content(repo, publish=True)
    words = client.get("/api/vocab/sets/a2-vetements").json()["words"]
    assert {w["status"] for w in words} == {"not_started"}
    client.post("/api/vocab/sets/a2-vetements/learn")
    words = client.get("/api/vocab/sets/a2-vetements").json()["words"]
    assert {w["status"] for w in words} == {"new"}
    assert words[0]["display"] == "la tuque" and words[0]["region"] == "qc"
