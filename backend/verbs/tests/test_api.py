import random
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as django_settings
from django.test import Client

from accounts.models import User
from contentkit.yamlio import dump_yaml
from curriculum import content
from verbs.models import ConjugationAttempt, VerbMastery
from verbs.services import build_drill

pytestmark = pytest.mark.django_db
REAL_REFERENCE = Path(django_settings.CONTENT_DIR) / "reference"

SETS = {
    "hidden": ["chier"],
    "sets": [
        {
            "id": "etre",
            "title": "Avec être",
            "title_en": "With être",
            "level": "A2",
            "description": "Movement verbs.",
            "verbs": ["aller", "partir", "venir"],
            "tenses": ["indicatif.passe_compose"],
        }
    ],
}
BANK = {
    "id": "partir",
    "content_version": 2,
    "infinitive": "partir",
    "en": "to leave",
    "sentences": [
        {
            "tense": "indicatif.passe_compose",
            "person": "il",
            "fr": "Hier soir, ma blonde est partie tard.",
            "form": "est partie",
            "en": "Last night my girlfriend left late.",
            "region": "qc",
        },
        {
            "tense": "indicatif.present",
            "person": "nous",
            "fr": "Nous partons au chalet vendredi.",
            "form": "partons",
            "en": "We're leaving for the cottage on Friday.",
        },
    ],
}


@pytest.fixture
def verb_client(client: Client, settings: Any, tmp_path: Path) -> tuple[Client, User]:
    if not (REAL_REFERENCE / "conjugations.json").exists():
        pytest.skip("conjugation reference not available")
    root = tmp_path / "content"
    root.mkdir()
    (root / "reference").symlink_to(REAL_REFERENCE)
    (root / "verbs" / "bank").mkdir(parents=True)
    (root / "verbs" / "sets.yaml").write_text(dump_yaml({"schema_version": 1, **SETS}))
    (root / "verbs" / "bank" / "partir.yaml").write_text(dump_yaml({"schema_version": 1, **BANK}))
    settings.CONTENT_DIR = root
    content.clear()
    user = User.objects.create_user("marie", password="pw-123456789")
    client.force_login(user)
    return client, user


def test_catalog_lists_sets_tenses_and_hides_vulgar_verbs(
    verb_client: tuple[Client, User],
) -> None:
    client, _ = verb_client
    body = client.get("/api/verbs").json()
    verbs = {v["infinitive"]: v for v in body["verbs"]}
    assert "chier" not in verbs
    assert verbs["partir"]["en"] == "to leave" and verbs["partir"]["sentences"] == 2
    assert verbs["aller"]["sets"] == ["etre"]
    assert body["sets"][0]["id"] == "etre"
    assert {t["key"] for t in body["tenses"]} >= {"indicatif.futur_proche", "subjonctif.passe"}
    assert client.get("/api/verbs/chier").status_code == 404


def test_verb_detail_has_table_examples_and_mastery(verb_client: tuple[Client, User]) -> None:
    client, user = verb_client
    VerbMastery.objects.create(user=user, infinitive="partir", tense="indicatif.present", ewma=0.5)
    body = client.get("/api/verbs/partir").json()
    assert body["auxiliary"] == "être" and body["participle_past"] == "parti"
    tenses = [t["tense"] for t in body["table"]]
    assert tenses[0] == "indicatif.present" and "indicatif.passe_simple" in tenses
    assert body["examples"][0]["tense_label"] == "Passé composé"
    assert body["mastery"] == [{"tense": "indicatif.present", "attempts": 0, "ewma": 0.5}]


def test_drill_items_do_not_leak_answers(verb_client: tuple[Client, User]) -> None:
    client, _ = verb_client
    response = client.post(
        "/api/verbs/drills",
        {"set": "etre", "tenses": ["indicatif.passe_compose"], "mode": "form", "count": 5},
        content_type="application/json",
    )
    items = response.json()["items"]
    assert len(items) == 5
    assert {i["infinitive"] for i in items} <= {"aller", "partir", "venir"}
    assert all(i["mode"] == "form" and i["sentence"] is None for i in items)
    assert "sommes" not in str(items) and "allé" not in str(items)


def test_context_drill_blanks_the_form(verb_client: tuple[Client, User]) -> None:
    _, user = verb_client
    items = build_drill(
        user,
        verbs=["partir"],
        tenses=["indicatif.passe_compose"],
        mode="context",
        count=1,
        rng=random.Random(1),
    )
    sentence = items[0]["sentence"]
    assert (sentence["before"], sentence["after"]) == ("Hier soir, ma blonde ", " tard.")
    assert items[0]["person"] == "il" and sentence["version"] == 2


def test_context_mode_without_sentences_is_an_error(verb_client: tuple[Client, User]) -> None:
    client, _ = verb_client
    response = client.post(
        "/api/verbs/drills",
        {"verbs": ["aller"], "tenses": ["indicatif.imparfait"], "mode": "context"},
        content_type="application/json",
    )
    assert response.status_code == 400


def test_answers_are_graded_recorded_and_update_mastery(
    verb_client: tuple[Client, User],
) -> None:
    client, user = verb_client
    sentence = {"bank": "partir", "version": 2, "index": 0}
    body = client.post(
        "/api/verbs/answers",
        {
            "answers": [
                {
                    "infinitive": "aller",
                    "tense": "indicatif.passe_compose",
                    "person": "je",
                    "answer": "j'ai allé",
                },
                {
                    "infinitive": "partir",
                    "tense": "indicatif.passe_compose",
                    "person": "il",
                    "answer": "est partie",
                    "sentence": sentence,
                },
            ]
        },
        content_type="application/json",
    ).json()
    wrong, right = body["results"]
    assert (wrong["result"], wrong["diagnosis"]) == ("incorrect", "wrong_auxiliary")
    assert wrong["expected"] == "je suis allé" and wrong["said"] == "je suis allé"
    assert right["correct"] and right["said"] == "Hier soir, ma blonde est partie tard."
    attempts = ConjugationAttempt.objects.filter(user=user).order_by("pk")
    assert [a.mode for a in attempts] == ["form", "context"]
    assert (attempts[1].sentence or {})["fr"].startswith("Hier soir")
    assert VerbMastery.objects.get(user=user, infinitive="aller").ewma == 0.0

    stale = client.post(
        "/api/verbs/answers",
        {
            "answers": [
                {
                    "infinitive": "partir",
                    "tense": "indicatif.passe_compose",
                    "person": "il",
                    "answer": "est partie",
                    "sentence": {**sentence, "version": 1},
                }
            ]
        },
        content_type="application/json",
    )
    assert stale.status_code == 400


def test_progress_lists_weak_spots(verb_client: tuple[Client, User]) -> None:
    client, user = verb_client
    VerbMastery.objects.create(
        user=user, infinitive="aller", tense="indicatif.passe_compose", attempts=4, ewma=0.2
    )
    VerbMastery.objects.create(
        user=user, infinitive="venir", tense="indicatif.present", attempts=4, ewma=0.95
    )
    body = client.get("/api/verbs/progress").json()
    assert [w["infinitive"] for w in body["weak_spots"]] == ["aller"]
    assert body["weak_spots"][0]["tense_label"] == "Passé composé"
