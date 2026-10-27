"""Step schemas the LLM fills during lesson generation. They omit ids and type tags (code
assigns those) so outputs stay small and focused; the generator converts them into
contentkit models."""

import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from contentkit.models import Example, Gender, RegionalVariant, VocabItem


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VocabDraft(Step):
    """LLM-facing vocabulary item. Unlike VocabItem, gender is *required* ("none" for non-nouns)
    so grammar-constrained decoding can't omit it for nouns."""

    fr: str = Field(description="The bare word or expression, without article")
    en: str
    pos: Literal["noun", "verb", "adjective", "adverb", "expression", "other"]
    gender: Literal["m", "f", "none"]
    region: Literal["qc", "fr", "common"]
    formality: Literal["formal", "standard", "familiar"]
    example_fr: str
    example_en: str


_ARTICLE = re.compile(r"^(?:(les|le|la|un|une|des)\s+|(l)['’]\s*)", re.IGNORECASE)
_ARTICLE_GENDER: dict[str, Gender] = {"le": "m", "un": "m", "la": "f", "une": "f"}


def vocab_item(draft: VocabDraft) -> VocabItem:
    """Deterministic clean-up: strip a leading article (inferring gender from it if needed)."""
    data = draft.model_dump(exclude={"gender"})
    gender: Gender | None = None if draft.gender == "none" else draft.gender
    if match := _ARTICLE.match(data["fr"]):
        article = (match.group(1) or "").lower()
        data["fr"] = data["fr"][match.end() :]
        gender = gender or _ARTICLE_GENDER.get(article)
    if data["pos"] == "noun" and gender is None:
        data["pos"] = "expression"  # no reliable gender: don't present it as a noun
    for key in ("example_fr", "example_en"):
        data[key] = data[key].strip() or None
    return VocabItem(gender=gender, **data)


class ExplanationStep(Step):
    title_en: str = Field(description="English translation of the lesson title")
    heading: str
    body: str = Field(description="Markdown, 150-300 words, English with French examples")


class TableStep(Step):
    include: bool = Field(description="false if no table would genuinely help")
    heading: str
    columns: list[str] = Field(min_length=2, max_length=5)
    rows: list[list[str]] = Field(min_length=1, max_length=12)
    caption: str


class ExamplesStep(Step):
    heading: str
    examples: list[Example] = Field(min_length=6, max_length=10)


class VocabularyStep(Step):
    heading: str
    items: list[VocabDraft] = Field(min_length=10, max_length=16)


class RegionalNoteStep(Step):
    heading: str
    body: str = Field(description="Markdown, 60-150 words")
    variants: list[RegionalVariant] = Field(max_length=6)


class ReadingStep(Step):
    title: str
    passage_fr: str
    translation_en: str
    glossary: list[VocabDraft] = Field(min_length=3, max_length=8)


# Field limits and descriptions keep larger models from packing a whole exercise (heading,
# numbered answers, hint) into one field.
Answer = Annotated[
    str, Field(max_length=200, description="One complete answer, with no notes or brackets")
]


class FillBlankDraft(Step):
    sentence: str = Field(max_length=200, description="French sentence containing exactly one ___")
    answers: list[Answer] = Field(min_length=1, max_length=3)
    hint: str = Field(
        max_length=160,
        description="Infinitive in parentheses when the blank is a verb, e.g. (aller); "
        "never the answer",
    )
    translation_en: str = Field(max_length=250)


class TranslateDraft(Step):
    prompt: str = Field(
        max_length=200,
        description="Only the one sentence to translate: no heading, answers or hint",
    )
    accepted_answers: list[Answer] = Field(min_length=2, max_length=4)
    hint: str = Field(max_length=160, description="One short line")


class ChoiceDraft(Step):
    question: str = Field(max_length=300)
    options: list[Annotated[str, Field(max_length=200)]] = Field(min_length=3, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str = Field(max_length=600)


def batch(item: type[Step], count: int) -> type[Step]:
    """A wrapper schema asking for exactly `count` items."""
    return type(
        f"{item.__name__}Batch{count}",
        (Step,),
        {
            "__annotations__": {"items": list[item]},  # type: ignore[valid-type]
            "items": Field(min_length=count, max_length=count),
        },
    )


def strip_article(item: VocabItem) -> VocabItem:
    """The same article clean-up for items that didn't come through VocabDraft (revisions)."""
    match = _ARTICLE.match(item.fr)
    if not match:
        return item
    gender = item.gender or _ARTICLE_GENDER.get((match.group(1) or "").lower())
    return item.model_copy(update={"fr": item.fr[match.end() :], "gender": gender})


_LATEX = {
    r"$\rightarrow$": "→",
    r"$\to$": "→",
    r"$\leftarrow$": "←",
    r"$\Rightarrow$": "⇒",
    r"\rightarrow": "→",
    r"\to ": "→ ",
    r"$\times$": "×",
    r"$\cdot$": "·",
    "\\n": "\n",  # a literal backslash-n from JSON escaped twice
    "\u2011": "-",  # non-breaking hyphen (gpt-oss): learners type « - »
    "\u00ad": "",  # soft hyphen inside a word (« déco\u00adrations »)
    # « \rightarrow » / « \to » left unescaped in JSON arrive as a carriage return / tab.
    "$\rightarrow$": "→",
    "\rightarrow": "→",
    "\to ": "→ ",
}


# Line breaks written as HTML or as stray symbols (« <br> », « ⟩⟩⟩ », « ⏎ »): the lesson
# renderer shows raw HTML as text.
_LINE_BREAK = re.compile(r"<br\s*/?>|⟩{2,}|⏎", re.I)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


_TABLE_RULE = re.compile(r"\|\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|")


def _split_table(line: str) -> str:
    """« text | A | B | |---|---| | a | b | » (a table flattened into one line) -> one row per
    line, with blank lines around the table."""
    rule = _TABLE_RULE.search(line)
    if not rule:
        return line
    columns = rule.group(0).count("|") - 1
    start, end = line.index("|"), line.rindex("|")
    cells = line[start + 1 : end].split("|")
    rows, i = [], 0
    while i < len(cells):
        rows.append("| " + " | ".join(c.strip() for c in cells[i : i + columns]) + " |")
        i += columns
        if i < len(cells) and not cells[i].strip():  # the « | | » between two rows
            i += 1
    parts = (line[:start].strip(), "\n".join(rows), line[end + 1 :].strip())
    return "\n\n".join(p for p in parts if p)


def unflatten_markdown(body: str) -> str:
    """gpt-oss sometimes writes a Markdown body on one line, with two spaces where the line
    breaks were and table rows run together; put the breaks back."""
    if "\n" not in body:
        body = re.sub(r" {2,}", "\n\n", body)
    body = re.sub(r"\*{5,}", "**", body)  # « *****Heading** »: a rule run into a bold heading
    return "\n".join(_split_table(line) for line in body.split("\n"))


def tidy(value: object, key: str = "") -> object:
    """Recursively replace LaTeX arrows and similar markup that small models emit in prose."""
    if isinstance(value, str):
        for latex, plain in _LATEX.items():
            value = value.replace(latex, plain)
        value = _HTML_COMMENT.sub("", _LINE_BREAK.sub("\n", value))
        return unflatten_markdown(value) if key == "body" else value
    if isinstance(value, list):
        return [tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: tidy(v, k) for k, v in value.items()}
    return value


class ReadingRevision(Step):
    """LLM-facing shape for revising a reading section (gender required, as in VocabDraft)."""

    type: Literal["reading"]
    id: str
    title: str
    passage_fr: str
    translation_en: str
    glossary: list[VocabDraft] = Field(min_length=3, max_length=8)


class VocabularyRevision(Step):
    type: Literal["vocabulary"]
    id: str
    heading: str
    items: list[VocabDraft] = Field(min_length=3, max_length=24)


def as_draft(item: VocabItem) -> dict[str, object]:
    data = item.model_dump(mode="json")
    data["gender"] = data.get("gender") or "none"
    data["example_fr"] = data.get("example_fr") or ""
    data["example_en"] = data.get("example_en") or ""
    return data


DRAFT_SHAPES: dict[str, tuple[type[Step], str]] = {
    "reading": (ReadingRevision, "glossary"),
    "vocabulary": (VocabularyRevision, "items"),
}
