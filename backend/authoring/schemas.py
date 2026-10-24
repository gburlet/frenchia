"""Step schemas the LLM fills during lesson generation. They omit ids and type tags (code
assigns those) so outputs stay small and focused; the generator converts them into
contentkit models."""

from pydantic import BaseModel, ConfigDict, Field

from contentkit.models import Example, RegionalVariant, VocabItem


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")


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
    items: list[VocabItem] = Field(min_length=10, max_length=16)


class RegionalNoteStep(Step):
    heading: str
    body: str = Field(description="Markdown, 60-150 words")
    variants: list[RegionalVariant] = Field(max_length=6)


class ReadingStep(Step):
    title: str
    passage_fr: str
    translation_en: str
    glossary: list[VocabItem] = Field(min_length=3, max_length=8)


class FillBlankDraft(Step):
    sentence: str = Field(description="French sentence containing exactly one ___")
    answers: list[str] = Field(min_length=1, max_length=3)
    hint: str = Field(
        description="Infinitive in parentheses when the blank is a verb, e.g. (aller)"
    )
    translation_en: str


class TranslateDraft(Step):
    prompt: str
    accepted_answers: list[str] = Field(min_length=2, max_length=4)
    hint: str


class ChoiceDraft(Step):
    question: str
    options: list[str] = Field(min_length=3, max_length=4)
    answer_index: int = Field(ge=0, le=3)
    explanation: str


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
