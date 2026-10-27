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


def test_comprehension_explanations_must_quote_the_passage() -> None:
    data = lesson_data()
    data["exercises"][2]["explanation"] = (
        "The text says: « Ils ont mangé une tourtière au chalet »."
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("quotes text that is not in the reading" in m for m in found)
    data["exercises"][2]["explanation"] = "The text says: « j'ai magasiné avec ma blonde »."
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []
    # Quoting an option, not the passage, is fine.
    data["exercises"][2]["options"][1] = "Ils ont dormi au chalet"
    data["exercises"][2]["explanation"] = "L'option B (« Ils ont dormi au chalet ») est fausse."
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []


def test_quebec_word_needs_a_bare_pattern_match() -> None:
    ref = Reference(Path("."))
    ref.quebec = [
        QuebecTerm(
            term="magasiner",
            match=[r"\bmagasin(er|e|ons)\b"],
            meaning="to shop",
            france="faire les magasins",
            formality="neutral",
        ),
        QuebecTerm(
            term="chauffer",
            match=[r"\bchauff(er|e)\b (son )?char\b"],
            meaning="to drive",
            france="conduire",
            formality="familiar",
        ),
    ]
    assert ref.is_quebec_word("magasiner")
    assert not ref.is_quebec_word("chauffer")
    assert ref.quebec_terms_in("chauffer")  # still a headword for vocabulary entries


def test_quebec_gender_wins_over_lexique() -> None:
    ref = Reference(Path("."))
    ref.nouns = {"party": {"gender": "f", "freq": 1.0}}
    ref.quebec = [
        QuebecTerm(
            term="party",
            match=[r"\bun party\b"],
            meaning="party",
            france="une fête",
            formality="familiar",
            gender="m",
        )
    ]
    assert ref.noun_gender("party") == "m"


def test_exercises_cannot_refer_to_formatting() -> None:
    data = lesson_data()
    data["exercises"][2]["question"] = "Que remplace le pronom souligné ?"
    issues = check_lesson_quality(Lesson.model_validate(data), reference())
    assert [(i.path, i.severity) for i in issues] == [
        ("a2-passe-compose-er:ex-03.question", "error")
    ]


def test_vulgar_words_are_errors() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["Il a le feu au cul.", "Il est pressé."]
    issues = check_lesson_quality(Lesson.model_validate(data), reference())
    assert [i.message for i in issues] == ["vulgar or swear word 'cul'"]
    data["exercises"][1]["accepted_answers"] = ["On a reculé.", "Nous avons reculé."]
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []


def test_hints_must_be_short_and_not_give_the_answer_away() -> None:
    data = lesson_data()
    data["exercises"][0]["hint"] = "Use « ai mangé »: avoir + participle."
    data["exercises"][1]["hint"] = "Remember:\n\nNote: on is common in Québec. " + "x" * 240
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert found == [
        "error:the hint gives away the answer 'ai mangé'",
        "error:the hint must be one short line (≤240 characters)",
    ]


def test_repeated_exercises_and_markup_are_errors() -> None:
    data = lesson_data()
    data["exercises"][2]["question"] = "Hier, j'___ une poutine ?"
    data["exercises"][1]["hint"] = "Not ~~On a magasiner~~"
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:repeats ex-01" in found
    assert "error:exercises are plain text: nothing is underlined or bold" in found
    data["exercises"][1]["hint"] = None
    data["exercises"][2]["question"] = "Qu'est-ce qu'ils ont fait ?"
    data["exercises"][2]["explanation"] = "« j'ai **magasiné** »"  # bold is rendered here
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []


def test_a_quoted_answer_in_the_hint_is_still_the_answer() -> None:
    data = lesson_data()
    data["exercises"][0]["sentence"] = "Le café ? Je ___ prends."
    data["exercises"][0]["answers"] = ["le"]
    data["exercises"][0]["hint"] = "Direct object pronoun 'le' replaces a masculine noun."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:the hint gives away the answer 'le'" in found


def test_answer_keys_must_be_real_french_words() -> None:
    ref = reference()
    ref.words = frozenset(
        {
            "hier",
            "une",
            "poutine",
            "aujourd'hui",
            "soeur",
            "magasiné",
            "nous",
            "avons",
            "mangé",
            "ont",
        }
    )
    data = lesson_data()
    data["exercises"][0]["sentence"] = "Aujourd'hui, ma sœur ___ une poutine."
    data["exercises"][0]["answers"] = ["ai bonned"]
    data["exercises"][0]["hint"] = None
    data["exercises"][1]["accepted_answers"] = ["On a magasiné.", "Nous avons magasiné."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), ref))
    assert found == ["error:'bonned' is not a French word (not in Lexique)"]
    data["exercises"][0]["answers"] = ["ai mangé"]
    assert check_lesson_quality(Lesson.model_validate(data), ref) == []
    data["exercises"][1]["accepted_answers"] = ["On a magasiné.", "L'ingénieure a magasiné."]
    assert check_lesson_quality(Lesson.model_validate(data), ref) == []  # feminine form


def test_quebec_meal_names_in_translations() -> None:
    data = lesson_data()
    translate = data["exercises"][1]
    translate.update(
        prompt="We had dinner at the restaurant.",
        accepted_answers=["On a soupé au restaurant.", "Nous avons dîné au restaurant."],
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert found == [
        "error:Québec meals: « dîné » is not 'dinner' (déjeuner = breakfast, "
        "dîner = lunch, souper = supper)"
    ]
    translate.update(prompt="I eat lunch at noon.", accepted_answers=["Je dîne à midi."])
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []
    translate.update(
        direction="fr_en",
        prompt="Le souper est meilleur que le dîner.",
        accepted_answers=["Supper is better than lunch."],
    )
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []
    translate.update(prompt="I eat breakfast.", accepted_answers=["Je prends mon petit-déjeuner."])
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []
    translate.update(
        direction="fr_en", prompt="Mon déjeuner était bon.", accepted_answers=["My lunch was good."]
    )
    assert (
        "Québec meals"
        in messages(check_lesson_quality(Lesson.model_validate(data), reference()))[0]
    )


def test_accepted_answers_carry_no_notes() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = [
        "On a magasiné.",
        "Nous avons fait du shopping. (France)",
    ]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert found == ["error:an accepted answer is a full answer, with no notes in brackets"]
    data["exercises"][1]["accepted_answers"] = ["On a magasiné.", "Québec : On a magasiné."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert found == ["error:an accepted answer is a full answer, with no « Québec : » label"]


def test_an_english_right_option_is_not_checked_as_french() -> None:
    ref = reference()
    ref.words = frozenset({"avoir", "chienne", "qu'est-ce", "veut", "dire"})
    data = lesson_data()
    data["exercises"][2] |= {"options": ["To be frightened or anxious.", "To own a dog."]}
    issues = check_lesson_quality(Lesson.model_validate(data), ref)
    assert not [i for i in issues if i.path.endswith("ex-03") and "French word" in i.message]


def test_doubled_subject_after_filling_is_an_error_but_reflexive_nous_is_not() -> None:
    data = lesson_data()
    blank = data["exercises"][0]
    blank |= {"sentence": "Je n'ai rien acheté parce qu'il ___ trop cher.", "answers": ["il était"]}
    blank["hint"] = None
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert found == ["error:word repeated after filling the blank with 'il était'"]
    blank |= {"sentence": "Ce matin, nous ___ tôt.", "answers": ["nous sommes levés"]}
    assert check_lesson_quality(Lesson.model_validate(data), reference()) == []


def test_a_gerondif_answer_is_a_verb_form() -> None:
    ref = reference()
    ref.verbs = {
        "jouer": {
            "participle_past": "joué",
            "participle_present": "jouant",
            "forms": {"indicatif.present": {"je": "joue"}},
        }
    }
    data = lesson_data()
    data["exercises"][0] |= {
        "sentence": "Il chante ___ au hockey.",
        "answers": ["en jouant"],
    }
    data["exercises"][0]["hint"] = "(jouer)"
    assert check_lesson_quality(Lesson.model_validate(data), ref) == []


def test_contraction_followed_by_an_article_is_an_error() -> None:
    data = lesson_data()
    data["exercises"][0] |= {"sentence": "Le parc est loin ___ centre-ville.", "answers": ["du le"]}
    data["exercises"][0]["hint"] = None
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:« du le »: du/au/aux already contain the article" in found
    data["exercises"][0] |= {"sentence": "Il y a ___ dans le frigo.", "answers": ["du lait"]}
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not [m for m in found if "already contain" in m]  # « du lait »


def test_meal_names_are_checked_in_example_sentences_too() -> None:
    data = lesson_data()
    data["sections"].append(
        {
            "type": "examples",
            "id": "examples",
            "heading": "Exemples",
            "examples": [
                {"fr": "Nous avons dîné tard.", "en": "We had dinner late."},
                {"fr": "J'ai mangé.", "en": "I ate."},
            ],
        }
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any(m.startswith("error:Québec meals: « dîné »") for m in found)


def test_missing_elision_and_week_end_are_errors() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["Parce que il pleut, on reste.", "On reste."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:missing elision: « Parce que il »" in found
    data["exercises"][1]["accepted_answers"] = ["Elle ne écrit pas.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:missing elision: « Elle ne écrit »" in found
    data["exercises"][1]["accepted_answers"] = ["Si j'avais su, je aurais agi.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:missing elision: « je aurais »" in found
    data["exercises"][1]["accepted_answers"] = ["On a magasiné ce week-end.", "On a magasiné."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:« ce week-end »: Québec usage is « la fin de semaine »" in found
    data["exercises"][1]["hint"] = "En France on dit « le week-end »."
    assert not [
        m
        for m in messages(check_lesson_quality(Lesson.model_validate(data), reference()))
        if "hint" in m and "week" in m
    ]


def test_other_france_forms_are_errors_in_french_text() -> None:
    data = lesson_data()
    for answer, word in [
        ("Je prends mon petit-déjeuner.", "petit-déjeuner"),
        ("Nous faisons du shopping.", "faisons du shopping"),
        ("Elle a envoyé un e-mail.", "e-mail"),
        ("Ce soir, nous préparons le dîner.", "dîner"),
        ("Le soir, nous dînerons chez Paul.", "dînerons"),
    ]:
        data["exercises"][1]["accepted_answers"] = [answer]
        found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
        assert any(m.startswith(f"error:« {word} »") for m in found), (answer, found)
    data["exercises"][1]["accepted_answers"] = ["En France, on dit petit-déjeuner."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not [m for m in found if "petit-déjeuner" in m]


def test_notes_about_the_brief_are_prompt_leaks() -> None:
    data = lesson_data()
    data["sections"][0]["body"] += " Based on the verified usage list."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("sections" in m or "mentions the generation instructions" in m for m in found)
    data = lesson_data()
    data["exercises"][1]["hint"] = "The word québécoise has been removed from the option."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data["exercises"][1]["hint"] = "Use « fin ». No regional note is needed here."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data = lesson_data()
    data["sections"][0]["body"] = (
        "This regional note has been removed because it contained unnecessary information."
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data["sections"][0]["body"] = "Below is the corrected table, as requested."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data = lesson_data()
    data["sections"][0]["heading"] = "Vocabulaire (10-16 items)"
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data = lesson_data()
    data["sections"][0]["body"] = "Finir: je finis… (truncated for brevity)"
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data["sections"][0]["body"] = "Use auquel after à. (removed meta text) Then practise."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found
    data["sections"][0]["body"] = "Québec speakers say « fais-toi-en pas » (region qc)."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("mentions the generation instructions" in m for m in found), found


def test_elision_is_checked_in_the_filled_sentence() -> None:
    data = lesson_data()
    data["exercises"][0] |= {"sentence": "On reste, ___ il pleut.", "answers": ["parce que"]}
    data["exercises"][0]["hint"] = None
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:missing elision once filled: « parce que il »" in found


def test_missing_contraction_after_a_compound_preposition() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["On a magasiné loin de le centre-ville.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:« loin de le »: de + le/les contract (du/des)" in found
    data["exercises"][1]["accepted_answers"] = ["On a essayé de le faire.", "On // France"]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not [m for m in found if "contract" in m]
    assert "error:an accepted answer is a full answer, with no notes in brackets" in found


def test_an_empty_or_degenerate_explanation_is_an_error() -> None:
    data = lesson_data()
    data["sections"][0]["body"] = "### Core {#core .untyped-1 .untyped-2 .untyped-3"
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert "error:the explanation is empty or broken markup" in found


def test_a_reading_that_translates_quebec_dîner_as_dinner_is_an_error() -> None:
    data = lesson_data()
    reading = next(s for s in data["sections"] if s["type"] == "reading")
    reading |= {
        "passage_fr": "Après le travail, nous avons dîné au restaurant du coin.",
        "translation_en": "After work, we had dinner at the corner restaurant.",
    }
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("« dîner » is lunch" in m for m in found), found
    reading["translation_en"] = "After work, we had lunch at the corner restaurant."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not any("Québec meals" in m for m in found), found


def test_en_after_the_auxiliary_is_an_error() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["Je me suis en allé.", "Je suis parti."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("en goes before the auxiliary" in m for m in found), found
    data["exercises"][1]["accepted_answers"] = ["Elle s'est en fait trompée.", "Je m'en suis allé."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not any("en goes before the auxiliary" in m for m in found), found


def test_a_pitfall_may_quote_the_mistake_and_hints_may_say_what_is_not_needed() -> None:
    data = lesson_data()
    data["sections"][0]["body"] += "\n\n- « Je en sors » is ungrammatical: say « J'en sors »."
    data["sections"][0]["body"] += "\n\nOn n'écrit pas « parce que il » : on écrit « parce qu'il »."
    data["exercises"][1]["hint"] = "Use s'en aller. No « de + event » is needed here."
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not any("elision" in m or "generation instructions" in m for m in found), found


def test_elision_before_a_consonant_is_an_error() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["Tu n' vas pas au parc.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("elision only before a vowel" in m for m in found), found
    data["exercises"][1]["accepted_answers"] = ["J'habite ici, l'hiver aussi.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert not any("elision only before a vowel" in m for m in found), found


def test_an_explanation_that_loops_is_an_error() -> None:
    data = lesson_data()
    data["sections"][0]["body"] = (
        "Les noms ont un genre. " + "Le déterminant indique le genre du nom. " * 4
    )
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("repeats itself" in m for m in found), found


def test_a_negated_verb_form_is_a_form_of_the_verb() -> None:
    from contentkit.validate import _is_verb_form

    forms = {"mange", "va", "vas", "a", "achetons"}
    for answer in ("ne mange", "n'a", "ne vas pas", "n'achetons"):
        assert _is_verb_form(answer, forms), answer
    assert not _is_verb_form("ne", forms)


def test_le_foot_is_adapted_to_québec_usage() -> None:
    data = lesson_data()
    data["exercises"][1]["accepted_answers"] = ["Mon fils joue au foot.", "Non."]
    found = messages(check_lesson_quality(Lesson.model_validate(data), reference()))
    assert any("« le soccer »" in m for m in found), found
