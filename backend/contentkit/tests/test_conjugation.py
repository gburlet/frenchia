from pathlib import Path

import pytest
from django.conf import settings

from contentkit.banks import check_verb_bank, uses_word
from contentkit.conjugation import (
    accepted_forms,
    conjugation_table,
    find_form,
    grade_conjugation,
    verb_slug,
    with_subject,
)
from contentkit.models import VerbBank
from contentkit.reference import Reference

REF = Reference.load(Path(settings.CONTENT_DIR))
pytestmark = pytest.mark.skipif(not REF.verbs, reason="conjugation reference not available")
PC = "indicatif.passe_compose"


@pytest.mark.parametrize(
    ("verb", "tense", "person", "answer", "result", "diagnosis"),
    [
        ("aller", PC, "nous", "sommes allés", "correct", ""),
        ("aller", PC, "nous", "nous sommes allées", "correct", ""),
        ("aller", PC, "je", "suis alle", "accent", "accents"),
        ("aller", PC, "il", "elle est allé", "incorrect", "agreement"),
        ("aller", PC, "je", "j'ai allé", "incorrect", "wrong_auxiliary"),
        ("prendre", PC, "il", "a prendu", "incorrect", "participle"),
        ("sortir", PC, "je", "j'ai sorti", "correct", ""),
        ("aller", "indicatif.present", "nous", "vont", "incorrect", "wrong_person"),
        ("aller", "indicatif.present", "nous", "allions", "incorrect", "wrong_tense"),
        ("manger", "indicatif.imparfait", "nous", "manger", "incorrect", "infinitive"),
        ("manger", "indicatif.imparfait", "nous", "mangeion", "incorrect", "spelling"),
        ("se lever", "indicatif.present", "je", "je me lève", "correct", ""),
        ("se lever", "indicatif.futur_proche", "nous", "nous allons nous lever", "correct", ""),
        ("s'asseoir", "indicatif.futur_proche", "je", "je vais m'asseoir", "correct", ""),
        ("payer", "indicatif.present", "je", "je paye", "correct", ""),
        ("payer", "indicatif.present", "je", "Je paie.", "correct", ""),
        ("parler", "subjonctif.present", "il", "qu'il parle", "correct", ""),
        ("finir", "imperatif.present", "tu", "finis", "correct", ""),
    ],
)
def test_grading(
    verb: str, tense: str, person: str, answer: str, result: str, diagnosis: str
) -> None:
    grade = grade_conjugation(REF, verb, tense, person, answer)
    assert (grade.result, grade.diagnosis) == (result, diagnosis), grade


def test_expected_answer_is_said_with_subject_and_masculine_by_default() -> None:
    assert grade_conjugation(REF, "aller", PC, "nous", "x").expected == "nous sommes allés"
    assert grade_conjugation(REF, "avoir", "indicatif.present", "je", "x").expected == "j'ai"
    assert grade_conjugation(REF, "aller", PC, "il", "elle est allé").expected == "elle est allée"


def test_context_sentence_fixes_agreement() -> None:
    grade = grade_conjugation(REF, "partir", PC, "il", "est parti", expected_form="est partie")
    assert (grade.result, grade.diagnosis, grade.expected) == (
        "incorrect",
        "agreement",
        "est partie",
    )
    assert grade_conjugation(REF, "partir", PC, "il", "est partie", expected_form="est partie")


def test_accepted_forms_include_agreement_and_both_auxiliaries() -> None:
    assert set(accepted_forms(REF, "aller", PC, "vous")) == {
        "êtes allés",
        "êtes allé",
        "êtes allées",
        "êtes allée",
    }
    assert "ai monté" in accepted_forms(REF, "monter", PC, "je")
    assert accepted_forms(REF, "parler", PC, "ils") == ["ont parlé"]


def test_find_form_and_helpers() -> None:
    assert find_form(REF, "partir", PC, "il", "Hier, Marie est partie tôt.") == "est partie"
    assert find_form(REF, "avoir", "indicatif.present", "je", "J’ai faim.") == "ai"
    assert find_form(REF, "aller", PC, "je", "Je vais au dépanneur.") is None
    assert verb_slug("s'asseoir") == "s-asseoir" and verb_slug("être") == "etre"
    assert with_subject("je", "me lève", "indicatif.present") == "je me lève"
    assert with_subject("il", "aille", "subjonctif.present") == "qu'il aille"
    table = {t["tense"]: t for t in conjugation_table(REF, "se lever")}
    assert table["indicatif.futur_proche"]["rows"][0]["said"] == "je vais me lever"
    assert len(table["imperatif.present"]["rows"]) == 3


def test_verb_bank_checks() -> None:
    bank = VerbBank.model_validate(
        {
            "id": "aller",
            "content_version": 1,
            "infinitive": "aller",
            "en": "to go",
            "sentences": [
                {
                    "tense": PC,
                    "person": "il",
                    "fr": "Ma blonde est allée au dépanneur.",
                    "form": "est allée",
                    "en": "My girlfriend went to the store.",
                    "region": "qc",
                },
                {
                    "tense": "indicatif.imparfait",
                    "person": "nous",
                    "fr": "Nous allons au chalet.",
                    "form": "allons",
                    "en": "We go to the cottage.",
                },
                {
                    "tense": "imperatif.present",
                    "person": "je",
                    "fr": "Va au lit !",
                    "form": "Va",
                    "en": "Go to bed!",
                },
            ],
        }
    )
    issues = check_verb_bank(bank, REF, "verbs/bank/aller.yaml")
    errors = [(i.path.split(":")[-1], i.message) for i in issues if i.severity == "error"]
    assert [path for path, _ in errors] == ["sentences.1", "sentences.2"]
    assert "Imparfait" in errors[0][1]


def test_find_form_needs_the_reflexive_pronoun_after_nous_and_vous() -> None:
    present = "indicatif.present"
    assert find_form(REF, "se lever", present, "nous", "Nous levons les rideaux.") is None
    assert find_form(REF, "se lever", present, "vous", "Vous vous levez tôt ?") == "vous levez"
    assert find_form(REF, "lever", present, "nous", "Nous levons les rideaux.") == "levons"


def test_gloss_is_not_a_sentence_translation() -> None:
    bank = VerbBank.model_validate(
        {
            "id": "choisir",
            "content_version": 1,
            "infinitive": "choisir",
            "en": "to choose",
            "sentences": [
                {
                    "tense": "indicatif.present",
                    "person": "nous",
                    "fr": "Nous choisissons un bon dessert pour ce soir.",
                    "form": "choisissons",
                    "en": "to choose",
                }
            ],
        }
    )
    issues = check_verb_bank(bank, REF, "verbs/bank/choisir.yaml")
    assert any("not a translation" in i.message for i in issues)


def test_uses_word_handles_elision_and_conjugated_expressions() -> None:
    assert uses_word("bien que", "Bien qu'il fasse froid, nous sortons.")
    assert uses_word("avoir mal à", "J'ai mal à la tête ce matin.")
    assert uses_word("cheval", "Les chevaux sont dans le champ.")
    assert not uses_word("tuque", "Il porte un chapeau.")
