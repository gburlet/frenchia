"""Pydantic schemas for content files. These are the single source of truth: JSON Schema in
content/schemas/ is exported from them, and they double as the LLM's structured-output
schemas during generation.

Files:
  content/curriculum/<level>.yaml   CurriculumLevel (units -> lesson outlines)
  content/grammar/topics.yaml       GrammarTopicRegistry
  content/lessons/<level>/<id>.yaml Lesson (sections + exercises)
  content/verbs/sets.yaml           VerbSetRegistry (drill sets of reference verbs)
  content/verbs/bank/<id>.yaml      VerbBank (gloss + context sentences for one verb)
  content/vocabulary/themes.yaml    VocabThemeRegistry (themed set outlines)
  content/vocabulary/sets/<id>.yaml VocabSet (one themed word list)
"""

import re
from datetime import datetime
from typing import Annotated, Final, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

SCHEMA_VERSION: Final = 1
BLANK = "___"

Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$", max_length=80)]
Level = Literal["A1", "A2", "B1", "B2", "C1", "C2"]
Region = Literal["qc", "fr", "common"]
Formality = Literal["formal", "standard", "familiar"]
Gender = Literal["m", "f"]
NonEmpty = Annotated[str, StringConstraints(min_length=1, strip_whitespace=True)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _unique(values: list[str], what: str) -> None:
    seen: set[str] = set()
    dupes = sorted({v for v in values if v in seen or seen.add(v)})  # type: ignore[func-returns-value]
    if dupes:
        raise ValueError(f"duplicate {what}: {', '.join(dupes)}")


# --- Curriculum outline -------------------------------------------------------------------

LessonKind = Literal[
    "pronunciation", "communication", "grammar", "vocabulary", "expressions", "review"
]


class LessonOutline(Model):
    id: Slug
    title: NonEmpty
    kind: LessonKind
    objectives: list[NonEmpty] = Field(min_length=1, max_length=4)
    grammar_topics: list[Slug] = []
    vocabulary_theme: str | None = None
    prerequisites: list[Slug] = []
    quebec_focus: str | None = None
    """One line on the Québec angle the lesson should include."""
    reference: str | None = None
    """Structural source, e.g. "clemence:day-31" (sequencing only; no text is reused)."""


class Unit(Model):
    id: Slug
    title: NonEmpty
    objectives: list[NonEmpty] = Field(min_length=1)
    lessons: list[LessonOutline] = Field(min_length=1)


class CurriculumLevel(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    level: Level
    title: NonEmpty
    summary: NonEmpty
    units: list[Unit] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        _unique([u.id for u in self.units], "unit ids")
        _unique([lesson.id for u in self.units for lesson in u.lessons], "lesson ids")
        return self


class GrammarTopic(Model):
    id: Slug
    level: Level
    title: NonEmpty
    related: list[Slug] = []


class GrammarTopicRegistry(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    topics: list[GrammarTopic]

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        _unique([t.id for t in self.topics], "grammar topic ids")
        return self


# --- Lesson sections ----------------------------------------------------------------------


class Example(Model):
    fr: NonEmpty
    en: NonEmpty
    note: str | None = None
    region: Region = "common"


class VocabItem(Model):
    fr: NonEmpty
    """Bare word or expression, without article."""
    en: NonEmpty
    pos: Literal["noun", "verb", "adjective", "adverb", "expression", "other"]
    gender: Gender | None = None
    region: Region = "common"
    formality: Formality = "standard"
    example_fr: str | None = None
    example_en: str | None = None

    @model_validator(mode="after")
    def _noun_gender(self) -> Self:
        if self.pos == "noun" and self.gender is None:
            raise ValueError(f"noun {self.fr!r} needs a gender")
        return self


class RegionalVariant(Model):
    qc: NonEmpty
    fr: NonEmpty
    en: NonEmpty
    formality: Formality = "standard"


class ExplanationSection(Model):
    type: Literal["explanation"]
    id: Slug
    heading: NonEmpty
    body: NonEmpty
    """Markdown, in English with French examples."""


class ExamplesSection(Model):
    type: Literal["examples"]
    id: Slug
    heading: NonEmpty
    examples: list[Example] = Field(min_length=2, max_length=12)


class TableSection(Model):
    type: Literal["table"]
    id: Slug
    heading: NonEmpty
    columns: list[NonEmpty] = Field(min_length=2, max_length=6)
    rows: list[list[str]] = Field(min_length=1, max_length=26)  # a whole alphabet
    caption: str | None = None

    @model_validator(mode="after")
    def _row_width(self) -> Self:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("every table row needs one cell per column")
        return self


class VocabularySection(Model):
    type: Literal["vocabulary"]
    id: Slug
    heading: NonEmpty
    items: list[VocabItem] = Field(min_length=3, max_length=24)


class ReadingSection(Model):
    type: Literal["reading"]
    id: Slug
    title: NonEmpty
    passage_fr: NonEmpty
    translation_en: NonEmpty
    glossary: list[VocabItem] = []


class RegionalNoteSection(Model):
    type: Literal["regional_note"]
    id: Slug
    heading: NonEmpty
    body: NonEmpty
    variants: list[RegionalVariant] = []


Section = Annotated[
    ExplanationSection
    | ExamplesSection
    | TableSection
    | VocabularySection
    | ReadingSection
    | RegionalNoteSection,
    Field(discriminator="type"),
]


# --- Exercises ----------------------------------------------------------------------------


class ExerciseBase(Model):
    id: Slug
    """Stable within the lesson (ex-01, ex-02, ...); globally "<lesson>/<id>"."""
    grammar_topics: list[Slug] = []


class TranslateExercise(ExerciseBase):
    type: Literal["translate"]
    direction: Literal["en_fr", "fr_en"]
    prompt: NonEmpty
    accepted_answers: list[NonEmpty] = Field(min_length=1, max_length=8)
    hint: str | None = None

    @model_validator(mode="after")
    def _distinct(self) -> Self:
        _unique([a.casefold() for a in self.accepted_answers], "accepted answers")
        return self


class FillBlankExercise(ExerciseBase):
    type: Literal["fill_blank"]
    sentence: NonEmpty
    """Contains exactly one ___ ."""
    answers: list[NonEmpty] = Field(min_length=1, max_length=4)
    hint: str | None = None
    """E.g. the infinitive: "(aller)"."""
    translation_en: NonEmpty

    @model_validator(mode="after")
    def _one_blank(self) -> Self:
        if self.sentence.count(BLANK) != 1:
            raise ValueError(f"fill_blank sentence needs exactly one {BLANK}: {self.sentence!r}")
        return self


class MultipleChoiceExercise(ExerciseBase):
    type: Literal["multiple_choice"]
    question: NonEmpty
    options: list[NonEmpty] = Field(min_length=2, max_length=5)
    answer_index: int = Field(ge=0)
    explanation: NonEmpty

    @model_validator(mode="after")
    def _answer_in_range(self) -> Self:
        if self.answer_index >= len(self.options):
            raise ValueError("answer_index out of range")
        # "J'ai mangé." and "J'ai mangé ?" are the same option to a learner.
        seen: dict[str, str] = {}
        for option in self.options:
            key = re.sub(r"[\W_]+", "", option.casefold())
            if key in seen:
                raise ValueError(
                    f"duplicate options: {seen[key]!r} and {option!r} differ only in "
                    "punctuation or case; every option must be a different answer"
                )
            seen[key] = option
        return self


class ComprehensionExercise(MultipleChoiceExercise):
    type: Literal["comprehension"]  # type: ignore[assignment]
    reading_id: Slug
    """Id of the reading section this question is about."""


Exercise = Annotated[
    TranslateExercise | FillBlankExercise | MultipleChoiceExercise | ComprehensionExercise,
    Field(discriminator="type"),
]


# --- Lesson -------------------------------------------------------------------------------


class Provenance(Model):
    generator: str
    """E.g. "ollama/gemma4:12b-it-qat"."""
    prompts: dict[str, str] = {}
    """Prompt id -> version used."""
    generated_at: datetime
    generated_hash: str
    """Content hash at generation time; a different current hash means manual edits."""
    reviewed_by: str | None = None
    """External proof-reader that reviewed this content (ADR 0003), if any."""
    job_id: int | None = None


class Lesson(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: Slug
    content_version: int = Field(ge=1)
    level: Level
    unit: Slug
    title: NonEmpty
    """French title."""
    title_en: NonEmpty
    objectives: list[NonEmpty] = Field(min_length=1, max_length=4)
    grammar_topics: list[Slug] = []
    region_focus: Region = "qc"
    estimated_minutes: int = Field(ge=5, le=90)
    sections: list[Section] = Field(min_length=1)
    exercises: list[Exercise] = []
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _internal_references(self) -> Self:
        _unique([s.id for s in self.sections], "section ids")
        _unique([e.id for e in self.exercises], "exercise ids")
        readings = {s.id for s in self.sections if isinstance(s, ReadingSection)}
        for ex in self.exercises:
            if isinstance(ex, ComprehensionExercise) and ex.reading_id not in readings:
                raise ValueError(f"exercise {ex.id} refers to unknown reading {ex.reading_id!r}")
        return self


# --- Verb Station -------------------------------------------------------------------------

TenseKey = Literal[
    "indicatif.present",
    "indicatif.futur_proche",
    "indicatif.passe_compose",
    "indicatif.imparfait",
    "indicatif.futur_simple",
    "imperatif.present",
    "conditionnel.present",
    "indicatif.plus_que_parfait",
    "subjonctif.present",
    "conditionnel.passe",
    "indicatif.futur_anterieur",
    "subjonctif.passe",
]
Person = Literal["je", "tu", "il", "nous", "vous", "ils"]


class VerbSet(Model):
    id: Slug
    title: NonEmpty
    title_en: NonEmpty
    level: Level
    description: NonEmpty
    verbs: list[NonEmpty] = Field(min_length=3)
    """Infinitives exactly as in content/reference/conjugations.json."""
    tenses: list[TenseKey] = Field(min_length=1)
    """Tenses suggested when drilling this set."""


class VerbSetRegistry(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    hidden: list[NonEmpty] = []
    """Reference verbs never offered for browsing or drills (vulgar or archaic)."""
    sets: list[VerbSet] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        _unique([s.id for s in self.sets], "verb set ids")
        return self


class VerbSentence(Model):
    tense: TenseKey
    person: Person
    fr: NonEmpty
    form: NonEmpty
    """The conjugated form exactly as written in `fr` (blanked out in context drills)."""
    en: NonEmpty
    region: Region = "common"

    @model_validator(mode="after")
    def _form_in_sentence(self) -> Self:
        if _fold(self.form) not in _fold(self.fr):
            raise ValueError(f"form {self.form!r} does not appear in {self.fr!r}")
        return self


class VerbBank(Model):
    """Gloss and context sentences for one reference verb (generated, then reviewed)."""

    schema_version: Literal[1] = SCHEMA_VERSION
    id: Slug
    content_version: int = Field(ge=1)
    infinitive: NonEmpty
    en: NonEmpty
    """English gloss, e.g. "to go"."""
    note: str | None = None
    sentences: list[VerbSentence] = Field(min_length=1, max_length=30)
    provenance: Provenance | None = None


def _fold(text: str) -> str:
    return " ".join(text.replace("’", "'").casefold().split())


# --- Vocabulary Station -------------------------------------------------------------------


class VocabTheme(Model):
    id: Slug
    level: Level
    title: NonEmpty
    """French title."""
    title_en: NonEmpty
    scope: NonEmpty
    """What the set covers, for the generator (one or two lines)."""
    quebec_focus: str | None = None
    size: int = Field(default=20, ge=8, le=40)


class VocabThemeRegistry(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    themes: list[VocabTheme] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> Self:
        _unique([t.id for t in self.themes], "theme ids")
        return self


class VocabEntry(Model):
    id: Slug
    fr: NonEmpty
    """Bare word or expression, without article."""
    en: NonEmpty
    pos: Literal["noun", "verb", "adjective", "adverb", "expression", "other"]
    gender: Gender | None = None
    plural: str | None = None
    """Only for irregular plurals (un œil -> des yeux)."""
    region: Region = "common"
    formality: Formality = "standard"
    example_fr: NonEmpty
    example_en: NonEmpty
    note: str | None = None
    """Usage note, e.g. the France equivalent of a Québec word."""

    @model_validator(mode="after")
    def _noun_gender(self) -> Self:
        if self.pos == "noun" and self.gender is None:
            raise ValueError(f"noun {self.fr!r} needs a gender")
        return self


class VocabSet(Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    id: Slug
    content_version: int = Field(ge=1)
    level: Level
    title: NonEmpty
    title_en: NonEmpty
    entries: list[VocabEntry] = Field(min_length=5, max_length=40)
    provenance: Provenance | None = None

    @model_validator(mode="after")
    def _unique_entries(self) -> Self:
        _unique([e.id for e in self.entries], "entry ids")
        return self
