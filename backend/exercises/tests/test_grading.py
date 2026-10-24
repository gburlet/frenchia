from pathlib import Path

from exercises.grading import (
    JudgeError,
    JudgeOutput,
    _from_judge,
    grade_choice,
    grade_fill_blank,
    grade_translate,
    normalize,
)
from inference.errors import InferenceUnavailable
from inference.fakes import FakeChatModel

TRANSLATE = {
    "type": "translate",
    "id": "ex-05",
    "direction": "en_fr",
    "prompt": "We had supper at six.",
    "accepted_answers": ["On a soupé à six heures.", "Nous avons soupé à six heures."],
}
FILL = {
    "type": "fill_blank",
    "id": "ex-04",
    "sentence": "Elle ___ à son ami.",
    "answers": ["a parlé"],
    "translation_en": "She spoke to her friend.",
}


def test_normalize_ignores_case_spacing_punctuation_and_apostrophe_style() -> None:
    assert normalize("  J’ai  mangé !") == normalize("j'ai mangé") == "j'ai mangé"
    assert normalize("« Bonjour », dit-il.") == "bonjour dit-il"


def test_choice_grading() -> None:
    mcq = {"type": "multiple_choice", "options": ["a", "b"], "answer_index": 1}
    assert grade_choice(mcq, 1).verdict == "correct"
    wrong = grade_choice(mcq, 0)
    assert (wrong.verdict, wrong.score) == ("incorrect", 0) and "« b »" in wrong.feedback["summary"]


def test_fill_blank_exact_accent_only_and_wrong() -> None:
    assert grade_fill_blank(FILL, "A parlé").verdict == "correct"
    accent = grade_fill_blank(FILL, "a parle")
    assert accent.verdict == "incorrect" and accent.feedback["accent_only"] and accent.score == 50
    wrong = grade_fill_blank(FILL, "a parler")
    assert wrong.feedback["corrected"] == "Elle a parlé à son ami."


def test_translate_accepted_answers_skip_the_llm() -> None:
    chat = FakeChatModel()
    assert (
        grade_translate(
            TRANSLATE, "nous avons soupé à six heures", level="A2", chat=chat, ref=None
        ).grading
        == "deterministic"
    )
    accent = grade_translate(TRANSLATE, "On a soupe a six heures.", level="A2", chat=chat, ref=None)
    assert accent.feedback["accent_only"] and accent.verdict == "incorrect"
    assert chat.calls == []


def test_translate_uses_llm_and_computes_verdict_from_errors() -> None:
    def responder(messages: object) -> str:
        return JudgeOutput(
            errors=[
                JudgeError(
                    category="preposition",
                    severity="error",
                    span="à 6h",
                    explanation="Use « à six heures ».",
                )
            ],
            corrected="On a soupé à six heures.",
            summary="Close!",
            register_note="",
        ).model_dump_json()

    chat = FakeChatModel(responder)
    result = grade_translate(TRANSLATE, "On a soupé à 6h", level="A2", chat=chat, ref=None)
    assert (result.grading, result.verdict, result.score) == ("llm", "incorrect", 50)
    assert result.feedback["errors"][0]["category"] == "preposition"
    prompt = chat.calls[0]["messages"][1].content
    assert "Learner answer: On a soupé à 6h" in prompt and "Before concluding" in prompt


def test_hallucinated_spans_are_dropped_and_minor_only_is_acceptable() -> None:
    output = JudgeOutput(
        errors=[
            JudgeError(
                category="agreement", severity="error", span="mangées", explanation="x"
            ),  # not in answer
            JudgeError(
                category="word_choice",
                severity="minor",
                span="On a",
                explanation="Nous is more formal.",
            ),
        ],
        corrected="On a mangé.",
        summary="Good.",
        register_note="Familiar « on ».",
    )
    grade = _from_judge(output, "On a mangé.", "m", 10)
    assert (
        grade.verdict == "acceptable" and grade.score == 85 and len(grade.feedback["errors"]) == 1
    )


def test_llm_down_gives_pending_with_reference() -> None:
    def down(messages: object) -> str:
        raise InferenceUnavailable("llm", "down")

    result = grade_translate(TRANSLATE, "On soupe", level="A2", chat=FakeChatModel(down), ref=None)
    assert (result.status, result.verdict) == ("pending", None)
    assert result.feedback["corrected"] == "On a soupé à six heures."


def test_quebec_lexicon_grounds_the_prompt() -> None:
    from contentkit.reference import QuebecTerm, Reference

    ref = Reference(Path("."))
    ref.quebec = [
        QuebecTerm(
            term="souper", match=[r"\bsoup"], meaning="supper", france="dîner", formality="standard"
        )
    ]
    chat = FakeChatModel(
        lambda m: JudgeOutput(
            errors=[], corrected="x", summary="ok", register_note=""
        ).model_dump_json()
    )
    grade_translate(TRANSLATE, "On soupe à six heures", level="A2", chat=chat, ref=ref)
    assert "souper: supper" in chat.calls[0]["messages"][1].content
