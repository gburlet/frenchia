"""Grading. Choice and fill-in-the-blank exercises are graded deterministically; translations
are graded deterministically when the answer matches an accepted answer (or only its accents
differ), and otherwise by the local LLM using the judge-v2 design from ADR 0002: the model
lists errors with a severity and the verdict is computed here, not taken from the model."""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

from contentkit.models import BLANK
from contentkit.reference import Reference
from inference.errors import InferenceError
from inference.llm import ChatModel, Message, complete_structured

PROMPT_VERSION = "judge-5"
CATEGORIES = (
    "agreement",
    "article",
    "preposition",
    "tense",
    "conjugation",
    "auxiliary",
    "pronoun_placement",
    "negation",
    "word_order",
    "word_choice",
    "spelling_accents",
    "register",
    "missing_or_extra",
    "meaning",
)
Category = Literal[
    "agreement",
    "article",
    "preposition",
    "tense",
    "conjugation",
    "auxiliary",
    "pronoun_placement",
    "negation",
    "word_order",
    "word_choice",
    "spelling_accents",
    "register",
    "missing_or_extra",
    "meaning",
]


@dataclass
class Grade:
    status: Literal["graded", "pending"]
    grading: Literal["deterministic", "llm", "pending"]
    verdict: Literal["correct", "acceptable", "incorrect"] | None
    score: int | None
    feedback: dict[str, Any] = field(default_factory=dict)
    model: str = ""
    latency_ms: int | None = None


# --- normalisation ------------------------------------------------------------------------

_PUNCT = re.compile(r"[^\w\s'-]")
_HYPHENS = str.maketrans({"\u2010": "-", "\u2011": "-"})


def normalize(text: str) -> str:
    """Case-, spacing- and punctuation-insensitive form (accents kept)."""
    text = unicodedata.normalize("NFC", text).casefold().replace("’", "'").replace("‘", "'")
    text = text.translate(_HYPHENS)  # « centre‑ville » (non-breaking hyphen) = centre-ville
    text = _PUNCT.sub(" ", text)
    return " ".join(text.split())


def strip_accents(text: str) -> str:
    text = text.replace("œ", "oe").replace("æ", "ae")
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _match(answer: str, accepted: list[str]) -> tuple[str | None, bool]:
    """(matching accepted answer, accent_only). Exact (normalised) match wins."""
    norm = normalize(answer)
    for candidate in accepted:
        if normalize(candidate) == norm:
            return candidate, False
    bare = strip_accents(norm)
    for candidate in accepted:
        if strip_accents(normalize(candidate)) == bare:
            return candidate, True
    return None, False


def _feedback(
    summary: str,
    *,
    corrected: str | None = None,
    accent_only: bool = False,
    errors: list[dict[str, str]] | None = None,
    register_note: str | None = None,
) -> dict[str, Any]:
    return {
        "summary": summary,
        "errors": errors or [],
        "corrected": corrected,
        "register_note": register_note,
        "accent_only": accent_only,
    }


# --- deterministic --------------------------------------------------------------------------


def grade_choice(payload: dict[str, Any], answer: int) -> Grade:
    correct = answer == payload["answer_index"]
    summary = (
        "Correct!"
        if correct
        else f"The answer is « {payload['options'][payload['answer_index']]} »."
    )
    return Grade(
        "graded",
        "deterministic",
        "correct" if correct else "incorrect",
        100 if correct else 0,
        _feedback(summary),
    )


def grade_fill_blank(payload: dict[str, Any], answer: str) -> Grade:
    match, accent_only = _match(answer, payload["answers"])
    corrected = payload["sentence"].replace(BLANK, match or payload["answers"][0])
    if match and not accent_only:
        return Grade(
            "graded", "deterministic", "correct", 100, _feedback("Correct!", corrected=corrected)
        )
    if accent_only:
        return Grade(
            "graded",
            "deterministic",
            "incorrect",
            50,
            _feedback(
                f"Almost: check the accents (« {match} »).", corrected=corrected, accent_only=True
            ),
        )
    return Grade(
        "graded",
        "deterministic",
        "incorrect",
        0,
        _feedback(f"The answer is « {payload['answers'][0]} ».", corrected=corrected),
    )


# --- translation ----------------------------------------------------------------------------


class JudgeError(BaseModel):
    category: Category
    severity: Literal["error", "minor"]
    span: str = Field(
        description="The exact wrong words copied from the learner answer ('' if missing words)"
    )
    explanation: str = Field(description="At most 20 words")


class JudgeOutput(BaseModel):
    errors: list[JudgeError] = Field(max_length=5)
    corrected: str = Field(
        description="The learner answer minimally corrected (unchanged if correct)"
    )
    register_note: str = Field(description="Register/Québec note, or empty")


# Output is what costs time (~21 tokens/s on the M2 Pro), so the schema asks for as little as
# possible and the summary is written in code. The instructions stay in the user turn after the
# case: moving them into the system message was faster but less accurate (ADR 0002 addendum).
SYSTEM = (
    "You are an expert French teacher for an English-speaking adult learning Québec French. "
    "Québec usage is the default: accept Québec vocabulary and natural informal spoken forms as "
    "correct (déjeuner = breakfast, dîner = lunch, souper = supper; la fin de semaine, en fin de "
    "semaine). Be precise and brief. Explanations are in English."
)
CHECKLIST = (
    "Before concluding there are no errors, check: gender/number agreement (adjectives, past "
    "participles with être and preceding direct objects); special forms before vowels (vieil, "
    "bel, nouvel, cet); articles (definite for general likes, partitive du/de la, de after "
    "negation, no article after être + profession); prepositions (à + city, en + feminine "
    "country, au/aux + masculine/plural country, verb + à/de); auxiliary (être verbs, pronominal "
    "verbs); tense choice (imparfait for habits/background, passé composé for completed events, "
    "depuis + présent); object pronoun placement and order; negation; accents that change "
    "meaning (a/à, ou/où)."
)
PROMPT = """\
Grade a CEFR {level} learner's translation from {source_lang} to {target_lang}.
Source: {source}
Reference translations (examples only; other correct wordings are fine): {references}
Learner answer: {answer}
{lexicon}
List every problem in the learner answer, at most 5. severity 'error' = anything a teacher would \
mark wrong (grammar, agreement, article, preposition, tense, spelling or accent, wrong meaning); \
'minor' = correct but slightly unnatural. Québec usage and informal spoken forms are correct: put \
register remarks in register_note, not in errors. Do not invent errors. {checklist}
Copy each error's span exactly from the learner answer. Keep every explanation under 12 words."""


def _lexicon_notes(ref: Reference | None, *texts: str) -> str:
    terms = ref.quebec_terms_in(*texts) if ref else []
    if not terms:
        return ""
    lines = "\n".join(f"- {t.term}: {t.meaning} (France: {t.france}; {t.formality})" for t in terms)
    return f"Verified Québec usage (authoritative):\n{lines}\n"


def grade_translate(
    payload: dict[str, Any],
    answer: str,
    *,
    level: str,
    chat: ChatModel | None,
    ref: Reference | None,
) -> Grade:
    accepted: list[str] = payload["accepted_answers"]
    match, accent_only = _match(answer, accepted)
    if match and not accent_only:
        return Grade(
            "graded", "deterministic", "correct", 100, _feedback("Correct!", corrected=match)
        )
    if accent_only:
        return Grade(
            "graded",
            "deterministic",
            "incorrect",
            60,
            _feedback(
                "Almost: only the accents differ.",
                corrected=match,
                accent_only=True,
                errors=[
                    {
                        "category": "spelling_accents",
                        "severity": "error",
                        "span": answer.strip(),
                        "explanation": f"Write « {match} ».",
                    }
                ],
            ),
        )
    if chat is None:
        return _pending(accepted)
    to_french = payload["direction"] == "en_fr"
    prompt = PROMPT.format(
        level=level,
        source_lang="English" if to_french else "French",
        target_lang="French" if to_french else "English",
        source=payload["prompt"],
        references=" | ".join(accepted),
        answer=answer.strip(),
        lexicon=_lexicon_notes(ref, payload["prompt"], answer, *accepted),
        checklist=CHECKLIST,
    )
    try:
        result, completion = complete_structured(
            chat, [Message("system", SYSTEM), Message("user", prompt)], JudgeOutput, max_tokens=500
        )
    except InferenceError:
        return _pending(accepted)
    return _from_judge(result, answer, chat.model, completion.latency_ms)


def _from_judge(result: JudgeOutput, answer: str, model: str, latency_ms: int) -> Grade:
    norm_answer = normalize(answer)
    errors = [
        e.model_dump()
        for e in result.errors
        # The model must quote the learner; a span that isn't in the answer is a hallucination.
        if not e.span.strip() or normalize(e.span) in norm_answer
    ]
    severities = {e["severity"] for e in errors}
    verdict: Literal["correct", "acceptable", "incorrect"]
    if "error" in severities:
        verdict, score = (
            "incorrect",
            max(0, 70 - 20 * sum(e["severity"] == "error" for e in errors)),
        )
    elif severities:
        verdict, score = "acceptable", 85
    else:
        verdict, score = "correct", 100
    corrected = result.corrected.strip() or None
    return Grade(
        "graded",
        "llm",
        verdict,
        score,
        _feedback(
            _summary(verdict, errors),
            corrected=corrected,
            errors=errors,
            register_note=_note(result.register_note),
        ),
        model=model,
        latency_ms=latency_ms,
    )


def _note(text: str) -> str | None:
    """Models sometimes write a placeholder instead of leaving the note empty."""
    text = text.strip()
    return None if text.casefold().strip(".") in {"", "none", "n/a", "na", "-", "null"} else text


SUMMARIES = {
    "correct": "Correct! Well done.",
    "acceptable": "Correct, with a small suggestion to sound more natural.",
}


def _summary(verdict: str, errors: list[dict[str, str]]) -> str:
    if verdict in SUMMARIES:
        return SUMMARIES[verdict]
    count = sum(e["severity"] == "error" for e in errors)
    return f"Not quite: {count} thing{'s' if count != 1 else ''} to fix." if count else "Not quite."


def _pending(accepted: list[str]) -> Grade:
    return Grade(
        "pending",
        "pending",
        None,
        None,
        _feedback(
            "Automatic feedback is unavailable right now (the local AI tutor isn't running). "
            "Compare with the reference answers, or retry in a moment.",
            corrected=accepted[0],
        ),
    )
