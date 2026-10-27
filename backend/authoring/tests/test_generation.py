import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from authoring.generation import (
    LessonBrief,
    LessonGenerator,
    LessonReviser,
    _emptied,
    gratuitous_quebec,
    verify_regions,
)
from authoring.schemas import tidy
from contentkit.models import (
    Example,
    ExamplesSection,
    FillBlankExercise,
    Lesson,
    LessonOutline,
    RegionalNoteSection,
)
from contentkit.reference import QuebecTerm, Reference
from contentkit.yamlio import content_hash
from inference.llm import Completion

from .scripted import ScriptedChat


def brief() -> LessonBrief:
    outline = LessonOutline(
        id="a2-passe-compose-er",
        title="Le passé composé des verbes en -er",
        kind="grammar",
        objectives=["Form the passé composé with avoir"],
        grammar_topics=["passe-compose-avoir"],
        quebec_focus="Weekend stories: magasiner, souper",
    )
    return LessonBrief(
        outline=outline,
        level="A2",
        unit_id="a2-u01-past",
        unit_title="Raconter au passé",
        topic_titles=["Passé composé with avoir"],
        prerequisite_titles=["Le présent"],
    )


def reference() -> Reference:
    ref = Reference(Path("."))
    ref.verbs = {
        "aller": {
            "participle_past": "allé",
            "participle_present": "allant",
            "forms": {"indicatif.passe_compose": {"il": "est allé"}},
        },
        "manger": {
            "participle_past": "mangé",
            "participle_present": "mangeant",
            "forms": {"indicatif.passe_compose": {"je": "ai mangé"}},
        },
    }
    ref.quebec = [
        QuebecTerm(
            term="magasiner",
            match=[r"\bmagasin"],
            meaning="to go shopping",
            france="faire du shopping",
            formality="standard",
        )
    ]
    return ref


def test_generates_a_valid_lesson_following_the_grammar_plan() -> None:
    progress: list[str] = []
    result = LessonGenerator(ScriptedChat(), reference(), progress.append).generate(
        brief(), content_version=3, job_id=7
    )
    lesson = result.lesson
    assert [s.type for s in lesson.sections] == [
        "explanation",
        "table",
        "examples",
        "regional_note",
        "reading",
    ]
    assert [e.id for e in lesson.exercises] == [f"ex-{i:02d}" for i in range(1, 13)]
    assert {e.type for e in lesson.exercises} == {
        "fill_blank",
        "translate",
        "multiple_choice",
        "comprehension",
    }
    assert all(e.grammar_topics == ["passe-compose-avoir"] for e in lesson.exercises)
    assert lesson.title_en == "The passé composé of -er verbs" and lesson.content_version == 3
    assert lesson.provenance is not None and lesson.provenance.job_id == 7
    assert lesson.provenance.generated_hash == content_hash(lesson)
    assert [i for i in result.issues if i.severity == "error"] == []
    assert progress[-1].startswith("Done")
    Lesson.model_validate(lesson.model_dump())  # round-trips


def test_context_includes_verified_quebec_usage() -> None:
    chat = ScriptedChat()
    LessonGenerator(chat, reference()).generate(brief(), content_version=1, job_id=None)
    first_prompt = chat.calls[0][1][1].content
    assert "Verified Québec usage" in first_prompt and "magasiner: to go shopping" in first_prompt


def test_deterministic_errors_trigger_one_repair() -> None:
    chat = ScriptedChat(bad_fill_first=True)
    generator = LessonGenerator(chat, reference())
    result = generator.generate(brief(), content_version=1, job_id=None)
    fill = next(e for e in result.lesson.exercises if isinstance(e, FillBlankExercise))
    assert fill.answers == ["est allée"]
    assert generator.stats.repairs == 1
    repair_prompt = next(
        m
        for t, ms in chat.calls
        if t.startswith("FillBlank")
        for m in ms
        if "previous answer" in m.content
    )
    assert "'a allé' is not a form of 'aller'" in repair_prompt.content


def test_reviser_changes_only_targets_and_keeps_ids() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference())
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    result = LessonReviser(ScriptedChat(), reference()).revise(
        lesson.model_dump(mode="json", exclude_none=True),
        "Use more Québec examples",
        ["table"],
        content_version=2,
        job_id=9,
    )
    revised = {s.id: s for s in result.lesson.sections}
    assert revised["table"].heading.endswith("(révisé)")  # type: ignore[union-attr]
    assert revised["explanation"] == next(s for s in lesson.sections if s.id == "explanation")
    assert [s.id for s in result.lesson.sections] == [s.id for s in lesson.sections]
    assert result.lesson.content_version == 2
    assert result.lesson.provenance and result.lesson.provenance.job_id == 9


def test_items_still_invalid_after_repair_are_dropped_with_a_warning() -> None:
    class DuplicateOptions(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            completion = super().complete(messages, json_schema=json_schema)
            if (json_schema or {}).get("title", "").startswith("ChoiceDraftBatch2"):
                data = json.loads(completion.content)
                data["items"][0]["options"] = ["pareil", "pareil", "autre"]
                return completion.__class__(content=json.dumps(data), model="x", latency_ms=1)
            return completion

    result = LessonGenerator(DuplicateOptions(), reference()).generate(
        brief(), content_version=1, job_id=None
    )
    assert sum(e.type == "multiple_choice" for e in result.lesson.exercises) == 1
    assert any(
        "dropped an invalid item: Value error, duplicate options" in i.message
        for i in result.issues
    )


def test_ai_critic_flags_graded_sentences_as_warnings() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    from authoring.critic import critique, sentences_to_check
    from contentkit.models import FillBlankExercise as FB

    first = next(e for e in lesson.exercises if isinstance(e, FB))
    bad = first.model_copy(update={"sentence": "Elle ___ son ami.", "answers": ["a parlé"]})
    lesson = lesson.model_copy(update={"exercises": [bad, *lesson.exercises[1:]]})
    assert ("ex-01", "Elle a parlé son ami.") in sentences_to_check(lesson)
    issues = critique(ScriptedChat(), lesson)
    assert [i.severity for i in issues] == ["warning"]
    assert "AI critic on 'Elle a parlé son ami.'" in issues[0].message


def test_options_differing_only_by_punctuation_are_duplicates() -> None:
    import pytest
    from pydantic import ValidationError

    from contentkit.models import MultipleChoiceExercise

    with pytest.raises(ValidationError, match="duplicate options"):
        MultipleChoiceExercise(
            type="multiple_choice",
            id="ex-01",
            question="?",
            answer_index=0,
            explanation="x",
            options=["J'ai mangé une pomme.", "J'ai mangé une pomme ?"],
        )


def test_reviser_repairs_items_that_no_longer_validate() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)
    mcq = next(e for e in data["exercises"] if e["type"] == "multiple_choice")
    mcq["options"] = ["J'ai mangé.", "J'ai mangé ?", "Je mange."]  # invalid under current rules

    class FixesOptions(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            completion = super().complete(messages, json_schema=json_schema)
            if (json_schema or {}).get("title") == "MultipleChoiceExercise":
                fixed = json.loads(completion.content)
                fixed["options"] = ["J'ai mangé.", "J'ai manger.", "Je mange."]
                return completion.__class__(content=json.dumps(fixed), model="x", latency_ms=1)
            return completion

    chat = FixesOptions()
    result = LessonReviser(chat, reference(), critic=False).revise(
        data, "Shorter explanation", ["explanation"], content_version=1, job_id=None
    )
    revised = next(e for e in result.lesson.exercises if e.id == mcq["id"])
    assert revised.options[1] == "J'ai manger."  # type: ignore[union-attr]
    prompt = next(ms[-1].content for t, ms in chat.calls if t == "MultipleChoiceExercise")
    assert 'currently invalid: Value error, duplicate options: "J\'ai mangé."' in prompt


def test_reviser_keeps_exercise_metadata() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)

    class DropsTopics(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            completion = super().complete(messages, json_schema=json_schema)
            if (json_schema or {}).get("title") == "FillBlankExercise":
                item = json.loads(completion.content)
                item["grammar_topics"] = []
                return completion.__class__(content=json.dumps(item), model="x", latency_ms=1)
            return completion

    result = LessonReviser(DropsTopics(), reference(), critic=False).revise(
        data, "Simplify", ["ex-01"], content_version=1, job_id=None
    )
    assert result.lesson.exercises[0].grammar_topics == ["passe-compose-avoir"]


def test_reviser_fills_missing_exercise_topics_from_the_lesson() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)
    data["exercises"][1]["grammar_topics"] = []
    result = LessonReviser(ScriptedChat(), reference(), critic=False).revise(
        data, "Tidy", ["table"], content_version=1, job_id=None
    )
    assert result.lesson.exercises[1].grammar_topics == ["passe-compose-avoir"]


def test_optional_table_still_invalid_after_repair_is_dropped() -> None:
    class RaggedTable(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            completion = super().complete(messages, json_schema=json_schema)
            if (json_schema or {}).get("title") == "TableStep":
                table = json.loads(completion.content)
                table["rows"] = [["j'", "ai", "extra"]]
                return completion.__class__(content=json.dumps(table), model="x", latency_ms=1)
            return completion

    result = LessonGenerator(RaggedTable(), reference(), critic=False).generate(
        brief(), content_version=1, job_id=None
    )
    assert "table" not in [s.type for s in result.lesson.sections]
    assert any("dropped invalid table" in i.message for i in result.issues)


def test_vocab_drafts_are_cleaned_deterministically() -> None:
    from authoring.schemas import VocabDraft, vocab_item

    def draft(fr: str, pos: str = "noun", gender: str = "none") -> VocabDraft:
        return VocabDraft.model_validate(
            {
                "fr": fr,
                "en": "x",
                "pos": pos,
                "gender": gender,
                "region": "qc",
                "formality": "standard",
                "example_fr": "",
                "example_en": "",
            }
        )

    assert (
        vocab_item(draft("La fin de semaine")).fr,
        vocab_item(draft("La fin de semaine")).gender,
    ) == ("fin de semaine", "f")
    assert vocab_item(draft("l'épicerie", gender="f")).fr == "épicerie"
    unknown = vocab_item(draft("les bas"))
    assert (unknown.fr, unknown.pos, unknown.gender) == (
        "bas",
        "expression",
        None,
    )  # no reliable gender
    assert vocab_item(draft("magasiner", pos="verb")).gender is None


def test_revisions_strip_glossary_articles() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)
    reading = next(s for s in data["sections"] if s["type"] == "reading")
    reading["glossary"][0] = {"fr": "le souper", "en": "supper", "pos": "noun", "gender": "m"}
    result = LessonReviser(ScriptedChat(), reference(), critic=False).revise(
        data, "Tidy", ["table"], content_version=1, job_id=None
    )
    revised = next(s for s in result.lesson.sections if s.type == "reading")
    assert revised.glossary[0].fr == "souper"


def test_latex_arrows_are_tidied() -> None:
    from authoring.schemas import tidy

    assert tidy({"body": ["parler $\\rightarrow$ parlé"]}) == {"body": ["parler → parlé"]}


def test_generated_hash_is_computed_after_tidying() -> None:
    class LatexExplanation(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            completion = super().complete(messages, json_schema=json_schema)
            if (json_schema or {}).get("title") == "ExplanationStep":
                step = json.loads(completion.content)
                step["body"] = "parler $\\rightarrow$ parlé"
                return completion.__class__(content=json.dumps(step), model="x", latency_ms=1)
            return completion

    lesson = (
        LessonGenerator(LatexExplanation(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    assert lesson.sections[0].body == "parler → parlé"  # type: ignore[union-attr]
    assert lesson.provenance and lesson.provenance.generated_hash == content_hash(lesson)


def test_reading_revisions_use_the_gender_required_shape() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)

    class RevisesReading(ScriptedChat):
        def complete(self, messages, *, json_schema=None, temperature=0.0, max_tokens=800):
            if (json_schema or {}).get("title") == "ReadingRevision":
                assert json_schema is not None
                assert "gender" in json_schema["$defs"]["VocabDraft"]["required"]
                current = json.loads(messages[-1].content.split("Current content (JSON):\n", 1)[1])
                current["glossary"][0].update(fr="le souper", gender="none", pos="noun")
                return Completion(content=json.dumps(current), model="x", latency_ms=1)
            return super().complete(messages, json_schema=json_schema)

    result = LessonReviser(RevisesReading(), reference(), critic=False).revise(
        data, "Fix the glossary", ["reading"], content_version=1, job_id=None
    )
    reading = next(s for s in result.lesson.sections if s.type == "reading")
    assert (reading.glossary[0].fr, reading.glossary[0].gender) == ("souper", "m")


class HintFixingChat(ScriptedChat):
    """Revises the fill-in exercise without fixing its hint; fixes it only when asked to repair."""

    def complete(self, messages: Any, **kwargs: Any) -> Completion:
        title = (kwargs.get("json_schema") or {}).get("title", "")
        if title == "FillBlankExercise":
            self.calls.append((title, list(messages)))
            current = json.loads(messages[-1].content.split("Current content (JSON):\n", 1)[1])
            if "gives away the answer" in messages[-1].content:
                current["hint"] = "(aller)"
            return Completion(json.dumps(current), self.model, 1, 10)
        return super().complete(messages, **kwargs)


def test_revision_repairs_what_the_checks_reject() -> None:
    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    data = lesson.model_dump(mode="json", exclude_none=True)
    fill = next(e for e in data["exercises"] if e["type"] == "fill_blank")
    fill["hint"] = f"Use « {fill['answers'][0]} »."
    chat = HintFixingChat()
    result = LessonReviser(chat, reference(), critic=False).revise(
        data, "Shorter hints", [fill["id"]], content_version=2, job_id=None
    )
    revised = next(e for e in result.lesson.exercises if e.id == fill["id"])
    assert revised.hint == "(aller)"  # type: ignore[union-attr]
    assert result.stats.repairs == 1
    assert not [i for i in result.issues if i.severity == "error"]


def test_only_lexicon_words_keep_a_quebec_tag() -> None:
    ref = Reference(Path("."))
    ref.quebec = [
        QuebecTerm(
            term="dépanneur",
            match=[r"\bdépanneur"],
            meaning="corner store",
            france="épicerie",
            formality="standard",
        )
    ]
    data = {
        "sections": [
            {
                "type": "vocabulary",
                "items": [
                    {"fr": "dépanneur", "region": "qc"},
                    {"fr": "quincaillerie", "region": "qc"},
                    {"fr": "le dépanneur", "region": "common"},
                    {"fr": "dépanneurs du coin", "region": "common"},
                ],
            },
            {
                "type": "examples",
                "examples": [
                    {"fr": "Je vais au dépanneur.", "region": "qc"},
                    {"fr": "Il fait beau.", "region": "qc"},
                ],
            },
        ]
    }
    data["sections"].append(
        {
            "type": "regional_note",
            "variants": [
                {"en": "corner store", "fr": "l'épicerie", "qc": "le dépanneur"},
                {"en": "hardware store", "fr": "la quincaillerie", "qc": "la quincaillerie"},
                # Supported by the lexicon but not used anywhere in the lesson: padding.
                {"en": "supper", "fr": "le dîner", "qc": "le souper"},
            ],
        }
    )
    out = verify_regions(data, ref)
    assert [v["qc"] for v in out["sections"][2]["variants"]] == ["le dépanneur"]
    assert [i["region"] for i in out["sections"][0]["items"]] == ["qc", "common", "qc", "common"]
    assert [e["region"] for e in out["sections"][1]["examples"]] == ["qc", "common"]


def test_tidy_turns_html_breaks_and_stray_symbols_into_newlines() -> None:
    assert tidy({"note": "| a |<br>|---|<br/>x⟩⟩⟩y⏎z<!-- note -->"}) == {
        "note": "| a |\n|---|\nx\ny\nz"
    }


def test_tidy_restores_line_breaks_in_a_flattened_body_only() -> None:
    flat = (
        "### Forms  Intro text.  | Verb | Form | |---|---| | parler | parlé | | finir | fini |  - a"
    )
    assert tidy({"body": flat, "fr": "Il  pleut."}) == {
        "body": "### Forms\n\nIntro text.\n\n| Verb | Form |\n| --- | --- |\n"
        "| parler | parlé |\n| finir | fini |\n\n- a",
        "fr": "Il  pleut.",
    }
    assert tidy({"body": "*****What they are**\nText"}) == {"body": "**What they are**\nText"}
    # A body that already has line breaks keeps its spacing.
    assert tidy({"body": "a  b\nc"}) == {"body": "a  b\nc"}


def test_tidy_turns_literal_backslash_n_into_a_newline() -> None:
    assert tidy({"body": "- les\\n- leur"}) == {"body": "- les\n- leur"}


def test_markdown_emphasis_is_dropped_from_exercises_but_not_explanations() -> None:
    from authoring.generation import plain_exercises

    data = {
        "exercises": [
            {"prompt": "Mon frère a vu **un castor**.", "explanation": "**Le castor** est m."}
        ]
    }
    assert plain_exercises(data)["exercises"][0] == {
        "prompt": "Mon frère a vu un castor.",
        "explanation": "**Le castor** est m.",
    }


def test_enumerators_are_dropped_from_options_and_prompts() -> None:
    from authoring.generation import plain_exercises

    data = {
        "exercises": [
            {"options": ["A. C'est le fun.", "B) C'est plate."], "prompt": "1️⃣ Après le souper."}
        ]
    }
    assert plain_exercises(data)["exercises"][0] == {
        "options": ["C'est le fun.", "C'est plate."],
        "prompt": "Après le souper.",
    }


def test_solver_flags_a_question_whose_key_it_cannot_reach() -> None:
    from authoring.critic import solve_choices

    class TwoRightAnswers(ScriptedChat):
        def complete(self, messages: Any, **kwargs: Any) -> Completion:
            if (kwargs.get("json_schema") or {}).get("title") == "Solution":
                return Completion('{"correct_options": [0, 1]}', self.model, 1, 5)
            return super().complete(messages, **kwargs)

    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    assert solve_choices(ScriptedChat(), lesson) == []  # agrees with every key
    flagged = solve_choices(TwoRightAnswers(), lesson)
    choices = [e for e in lesson.exercises if e.type in ("multiple_choice", "comprehension")]
    assert len(flagged) == len(choices) and "correct option(s) [0, 1]" in flagged[0].message
    assert flagged[0].message.startswith("AI critic")  # so auto-review revises it


def test_blank_checker_flags_other_answers_and_off_topic_blanks() -> None:
    from authoring.critic import check_blanks

    class Picky(ScriptedChat):
        def complete(self, messages: Any, **kwargs: Any) -> Completion:
            if (kwargs.get("json_schema") or {}).get("title") == "BlankCheck":
                body = {
                    "other_accepted_answers": ["Est allée", "y est allée"],
                    "tests_the_lesson_point": False,
                    "problem": "Tests a place, not y.",
                }
                return Completion(json.dumps(body), self.model, 1, 5)
            return super().complete(messages, **kwargs)

    lesson = (
        LessonGenerator(ScriptedChat(), reference(), critic=False)
        .generate(brief(), content_version=1, job_id=None)
        .lesson
    )
    assert check_blanks(ScriptedChat(), lesson, ["Use y"]) == []
    flagged = check_blanks(Picky(), lesson, ["Use y"])
    first = flagged[0].message
    assert "also accept ['y est allée']" in first  # « Est allée » is the key itself
    assert "does not practise the lesson's point" in first and first.startswith("AI critic")


def test_gender_notation_in_answers_becomes_two_answers() -> None:
    from authoring.generation import plain_item

    data = {"accepted_answers": ["Tu serais allé(e) hier.", "Tu serais allé hier."]}
    assert plain_item(data)["accepted_answers"] == ["Tu serais allé hier.", "Tu serais allée hier."]


def plain_brief(**outline: Any) -> LessonBrief:
    """A brief without a Québec angle (most lessons)."""
    base = brief()
    fields = {**base.outline.model_dump(), "quebec_focus": None, **outline}
    return replace(base, outline=LessonOutline(**fields))


def test_lessons_without_a_quebec_angle_get_no_regional_note() -> None:
    chat = ScriptedChat()
    lesson = (
        LessonGenerator(chat, reference())
        .generate(plain_brief(), content_version=1, job_id=None)
        .lesson
    )
    assert "regional_note" not in [s.type for s in lesson.sections]
    assert "Québec angle" not in chat.calls[0][1][1].content


def examples(*sentences: str) -> ExamplesSection:
    return ExamplesSection(
        type="examples",
        id="examples",
        heading="Exemples",
        examples=[Example(fr=s, en="x") for s in sentences],
    )


def test_quebec_emblems_off_topic_are_problems() -> None:
    section = examples("Il aurait acheté du lait au dépanneur.", "Nous aurions vu le match.")
    [problem] = gratuitous_quebec(plain_brief(), [section], [], reference())
    assert "dépanneur" in problem and "local colour" in problem
    shopping = plain_brief(objectives=["Talk about shopping in your quartier"])
    assert gratuitous_quebec(shopping, [section], [], reference()) == []


def test_one_quebec_term_repeated_across_the_lesson_is_a_problem() -> None:
    section = examples(*(f"Elle magasine le {d}." for d in ("lundi", "mardi", "jeudi", "samedi")))
    [problem] = gratuitous_quebec(plain_brief(), [section], [], reference())
    assert "magasiner" in problem and "4 French sentences" in problem
    three = examples(*(e.fr for e in section.examples[:3]))
    assert gratuitous_quebec(plain_brief(), [three], [], reference()) == []


def test_plain_french_tagged_as_france_usage_becomes_common() -> None:
    data: dict[str, Any] = {
        "sections": [
            {
                "type": "examples",
                "examples": [
                    {"fr": "Il a fini son rapport.", "en": "x", "region": "fr"},
                    {"fr": "On part en week-end.", "en": "x", "region": "fr"},
                ],
            }
        ]
    }
    verify_regions(data, reference())
    assert [e["region"] for e in data["sections"][0]["examples"]] == ["common", "fr"]


def test_a_regional_note_the_reviser_emptied_is_dropped() -> None:
    def note(body: str) -> RegionalNoteSection:
        return RegionalNoteSection(
            type="regional_note", id="regional-note", heading="Québec", body=body
        )

    assert _emptied(note("This regional note has been removed because it was not needed."))
    assert not _emptied(
        note("Québec speakers often say « fait que » where France says « du coup ».")
    )


def test_tidy_drops_markdown_marks_from_headings_and_zero_width_characters() -> None:
    assert tidy({"heading": "## Le ne explétif", "body": "Après\u200b avant que"}) == {
        "heading": "Le ne explétif",
        "body": "Après avant que",
    }
    assert tidy({"note": "Forming words \u202fn\u200bn1. re-"}) == {
        "note": "Forming words\n\n1. re-"
    }
