"""Lesson generation with the local LLM: a fixed plan per lesson kind, one small
schema-constrained call per section or exercise batch, deterministic checks after each step
(with one repair attempt), and full-lesson validation at the end.

Plain Python on top of ChatModel/Reference: no Django, so it is testable with fakes."""

import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ValidationError

from contentkit.models import (
    ComprehensionExercise,
    ExamplesSection,
    ExplanationSection,
    FillBlankExercise,
    Lesson,
    LessonOutline,
    Level,
    MultipleChoiceExercise,
    Provenance,
    ReadingSection,
    RegionalNoteSection,
    TableSection,
    TranslateExercise,
    VocabItem,
    VocabularySection,
)
from contentkit.reference import Reference
from contentkit.validate import Issue, check_lesson_quality
from contentkit.yamlio import content_hash
from inference.errors import InvalidOutput
from inference.llm import ChatModel, Message, complete_structured

from . import prompts
from .critic import critique
from .schemas import (
    DRAFT_SHAPES,
    ChoiceDraft,
    ExamplesStep,
    ExplanationStep,
    FillBlankDraft,
    ReadingStep,
    RegionalNoteStep,
    Step,
    TableStep,
    TranslateDraft,
    VocabularyStep,
    as_draft,
    batch,
    strip_article,
    tidy,
    vocab_item,
)


@dataclass(frozen=True)
class Plan:
    sections: tuple[str, ...]
    exercises: tuple[tuple[str, int], ...]


PLANS: dict[str, Plan] = {
    "grammar": Plan(
        ("explanation", "table", "examples", "regional_note", "reading"),
        (
            ("fill_blank", 4),
            ("translate_en_fr", 3),
            ("translate_fr_en", 1),
            ("multiple_choice", 2),
            ("comprehension", 2),
        ),
    ),
    "vocabulary": Plan(
        ("explanation", "vocabulary", "examples", "regional_note", "reading"),
        (
            ("translate_en_fr", 3),
            ("translate_fr_en", 2),
            ("multiple_choice", 3),
            ("comprehension", 2),
        ),
    ),
    "expressions": Plan(
        ("explanation", "vocabulary", "examples", "reading"),
        (("multiple_choice", 4), ("translate_fr_en", 3), ("comprehension", 2)),
    ),
    "pronunciation": Plan(
        ("explanation", "table", "examples", "reading"),
        (("multiple_choice", 4), ("translate_fr_en", 2), ("comprehension", 2)),
    ),
    "communication": Plan(
        ("explanation", "examples", "regional_note", "reading"),
        (("translate_en_fr", 3), ("fill_blank", 2), ("multiple_choice", 2), ("comprehension", 2)),
    ),
    "review": Plan(
        ("explanation", "table", "examples", "reading"),
        (("fill_blank", 4), ("multiple_choice", 3), ("translate_en_fr", 3), ("comprehension", 2)),
    ),
}

SECTION_STEPS: dict[str, type[BaseModel]] = {
    "explanation": ExplanationStep,
    "table": TableStep,
    "examples": ExamplesStep,
    "vocabulary": VocabularyStep,
    "regional_note": RegionalNoteStep,
    "reading": ReadingStep,
}
MAX_TOKENS = 1800
OPTIONAL_SECTIONS = {"table"}

SECTION_TYPES: dict[str, type[BaseModel]] = {
    "explanation": ExplanationSection,
    "examples": ExamplesSection,
    "table": TableSection,
    "vocabulary": VocabularySection,
    "reading": ReadingSection,
    "regional_note": RegionalNoteSection,
}
EXERCISE_TYPES: dict[str, type[BaseModel]] = {
    "translate": TranslateExercise,
    "fill_blank": FillBlankExercise,
    "multiple_choice": MultipleChoiceExercise,
    "comprehension": ComprehensionExercise,
}


@dataclass
class LessonBrief:
    """Everything the generator needs to know about the curriculum slot."""

    outline: LessonOutline
    level: Level
    unit_id: str
    unit_title: str
    topic_titles: list[str]
    prerequisite_titles: list[str]


@dataclass
class Stats:
    calls: int = 0
    seconds: float = 0.0
    tokens: int = 0
    repairs: int = 0

    def record(self, seconds: float, tokens: int) -> None:
        self.calls += 1
        self.seconds += seconds
        self.tokens += tokens


@dataclass
class GenerationResult:
    lesson: Lesson
    issues: list[Issue]
    stats: Stats
    prompts: dict[str, str] = field(default_factory=lambda: dict(prompts.PROMPT_VERSIONS))


Progress = Callable[[str], None]


class LessonGenerator:
    def __init__(
        self,
        chat: ChatModel,
        ref: Reference,
        progress: Progress | None = None,
        *,
        critic: bool = True,
    ) -> None:
        self.chat = chat
        self.ref = ref
        self.progress = progress or (lambda message: None)
        self.critic = critic
        self.stats = Stats()
        self.dropped: list[Issue] = []

    # --- public API ------------------------------------------------------------------------

    def generate(
        self, brief: LessonBrief, *, content_version: int, job_id: int | None
    ) -> GenerationResult:
        plan = PLANS[brief.outline.kind]
        context = self._context(brief)
        sections: list[Any] = []
        title_en = brief.outline.title
        for step in plan.sections:
            self.progress(f"Writing {step.replace('_', ' ')}")
            section, extra = self._section(step, brief, context, sections)
            if section is not None:
                sections.append(section)
            title_en = extra.get("title_en", title_en)
        exercises: list[Any] = []
        for step, count in plan.exercises:
            self.progress(f"Writing {count} {step.replace('_', ' ')} exercises")
            exercises += self._exercises(step, count, brief, context, sections)
        exercises = [
            ex.model_copy(update={"id": f"ex-{i:02d}"}) for i, ex in enumerate(exercises, 1)
        ]
        lesson = self._assemble(brief, sections, exercises, title_en, content_version, job_id)
        issues = [*self.dropped, *check_lesson_quality(lesson, self.ref)]
        if self.critic:
            self.progress("AI critic: proof-reading graded French sentences")
            issues += critique(self.chat, lesson, self.stats.record)
        self.progress(
            f"Done: {len(sections)} sections, {len(exercises)} exercises, "
            f"{sum(i.severity == 'error' for i in issues)} errors"
        )
        return GenerationResult(lesson, issues, self.stats)

    # --- steps -----------------------------------------------------------------------------

    def _section(
        self, step: str, brief: LessonBrief, context: str, sections: list[Any]
    ) -> tuple[Any, dict[str, str]]:
        schema = SECTION_STEPS[step]
        instruction = prompts.STEPS[step].format(
            words=prompts.READING_WORDS.get(brief.level, "150"), level=brief.level
        )
        extra: dict[str, str] = {}

        def convert(obj: Any) -> Any:
            data = obj.model_dump()
            if step == "explanation":
                extra["title_en"] = data.pop("title_en")
                return ExplanationSection(type="explanation", id="explanation", **data)
            if step == "table":
                if not data.pop("include"):
                    return None
                return TableSection(type="table", id="table", **data)
            builders = {
                "examples": (ExamplesSection, "examples"),
                "vocabulary": (VocabularySection, "vocabulary"),
                "regional_note": (RegionalNoteSection, "regional-note"),
                "reading": (ReadingSection, "reading"),
            }
            model, section_id = builders[step]
            if step == "vocabulary":
                data["items"] = [vocab_item(item) for item in obj.items]
            elif step == "reading":
                data["glossary"] = [vocab_item(item) for item in obj.glossary]
            return model(type=step, id=section_id, **data)

        def check(obj: Any) -> list[str]:
            section = convert(obj)
            return [] if section is None else self._problems(brief, [*sections, section], [])

        obj = self._ask(context, sections, instruction, schema, check)
        try:
            return convert(obj), extra
        except ValidationError as exc:
            if step not in OPTIONAL_SECTIONS:
                raise
            # An optional section that is still invalid after repair is dropped, not fatal.
            message = exc.errors()[0]["msg"]
            self.dropped.append(
                Issue("warning", f"{brief.outline.id}:{step}", f"dropped invalid {step}: {message}")
            )
            return None, extra

    def _exercises(
        self, step: str, count: int, brief: LessonBrief, context: str, sections: list[Any]
    ) -> list[Any]:
        reading = next((s for s in sections if isinstance(s, ReadingSection)), None)
        if step == "comprehension" and reading is None:
            return []
        drafts: dict[str, type[Step]] = {
            "fill_blank": FillBlankDraft,
            "translate_en_fr": TranslateDraft,
            "translate_fr_en": TranslateDraft,
        }
        draft = drafts.get(step, ChoiceDraft)
        instruction = prompts.STEPS[step].format(
            count=count, passage=reading.passage_fr if reading else ""
        )
        topics = list(brief.outline.grammar_topics)

        def convert_item(i: int, item: Any) -> Any:
            data: dict[str, Any] = {
                **item.model_dump(),
                "id": f"{step.replace('_', '-')}-{i}",
                "grammar_topics": topics,
            }
            if step == "fill_blank":
                return FillBlankExercise.model_validate({**data, "type": "fill_blank"})
            if step.startswith("translate"):
                direction = step.removeprefix("translate_")
                return TranslateExercise.model_validate(
                    {**data, "type": "translate", "direction": direction}
                )
            if step == "comprehension" and reading is not None:
                return ComprehensionExercise.model_validate(
                    {**data, "type": "comprehension", "reading_id": reading.id}
                )
            return MultipleChoiceExercise.model_validate({**data, "type": "multiple_choice"})

        def convert(obj: Any) -> list[Any]:
            return [convert_item(i, item) for i, item in enumerate(obj.items)]

        def check(obj: Any) -> list[str]:
            return self._problems(brief, sections, convert(obj))

        obj = self._ask(context, sections, instruction, batch(draft, count), check)
        kept = []
        for i, item in enumerate(obj.items):
            try:
                kept.append(convert_item(i, item))
            except ValidationError as exc:
                # One bad item should not sink a whole lesson: drop it and tell the reviewer.
                message = exc.errors()[0]["msg"]
                self.dropped.append(
                    Issue(
                        "warning",
                        f"{brief.outline.id}:{step}",
                        f"dropped an invalid item: {message}",
                    )
                )
        return kept

    # --- LLM plumbing ----------------------------------------------------------------------

    def _ask(
        self,
        context: str,
        sections: Sequence[Any],
        instruction: str,
        schema: type[BaseModel],
        check: Callable[[Any], list[str]],
    ) -> Any:
        user = context + self._so_far(sections) + "\n" + instruction
        messages = [Message("system", prompts.SYSTEM), Message("user", user)]
        obj = self._call(messages, schema)
        problems = self._safe_check(check, obj)
        if problems:
            self.stats.repairs += 1
            self.progress(f"Repairing: {'; '.join(problems)[:200]}")
            retry = [
                *messages,
                Message("assistant", obj.model_dump_json()),
                Message(
                    "user", prompts.REPAIR.format(problems="\n".join(f"- {p}" for p in problems))
                ),
            ]
            fixed = self._call(retry, schema)
            if len(self._safe_check(check, fixed)) < len(problems):
                obj = fixed
        return obj

    def _call(self, messages: list[Message], schema: type[BaseModel]) -> Any:
        started = time.perf_counter()
        obj, completion = complete_structured(
            self.chat, messages, schema, max_tokens=MAX_TOKENS, temperature=0.4
        )
        self.stats.calls += 1
        self.stats.seconds += time.perf_counter() - started
        self.stats.tokens += completion.completion_tokens or 0
        return obj

    @staticmethod
    def _safe_check(check: Callable[[Any], list[str]], obj: Any) -> list[str]:
        try:
            return check(obj)
        except ValidationError as exc:
            return [f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()]

    def _problems(self, brief: LessonBrief, sections: list[Any], exercises: list[Any]) -> list[str]:
        if not sections:
            sections = [
                ExplanationSection(type="explanation", id="placeholder", heading="x", body="x")
            ]
        partial = Lesson(
            id=brief.outline.id,
            content_version=1,
            level=brief.level,
            unit=brief.unit_id,
            title=brief.outline.title,
            title_en="x",
            objectives=list(brief.outline.objectives),
            estimated_minutes=10,
            sections=sections,
            exercises=exercises,
        )
        return [
            f"{i.path.split(':', 1)[1]}: {i.message}"
            for i in check_lesson_quality(partial, self.ref)
            if i.severity == "error"
        ]

    # --- context -----------------------------------------------------------------------------

    def _context(self, brief: LessonBrief) -> str:
        o = brief.outline
        lexicon_terms = self.ref.quebec_terms_in(
            o.title, o.quebec_focus or "", o.vocabulary_theme or "", *o.objectives
        )
        lexicon = (
            prompts.LEXICON.format(
                entries="\n".join(
                    f"- {t.term}: {t.meaning} (France: {t.france}; {t.formality})"
                    for t in lexicon_terms
                )
            )
            if lexicon_terms
            else ""
        )
        return prompts.CONTEXT.format(
            title=o.title,
            id=o.id,
            level=brief.level,
            kind=o.kind,
            unit_title=brief.unit_title,
            objectives="\n".join(f"- {x}" for x in o.objectives),
            topics=", ".join(brief.topic_titles) or "none",
            theme=o.vocabulary_theme or "none",
            quebec_focus=o.quebec_focus or "use Québec usage where natural",
            prerequisites=", ".join(brief.prerequisite_titles) or "nothing specific",
            lexicon=lexicon,
        )

    @staticmethod
    def _so_far(sections: Sequence[Any]) -> str:
        if not sections:
            return ""
        parts = []
        for s in sections:
            if isinstance(s, ExplanationSection):
                parts.append(f"[explanation] {s.heading}: {s.body[:500]}")
            elif isinstance(s, ExamplesSection):
                parts.append("[examples] " + " | ".join(e.fr for e in s.examples))
            elif isinstance(s, VocabularySection):
                parts.append("[vocabulary] " + ", ".join(i.fr for i in s.items))
            elif isinstance(s, ReadingSection):
                parts.append(f"[reading] {s.title}: {s.passage_fr[:400]}")
            else:
                parts.append(f"[{s.type}] {getattr(s, 'heading', '')}")
        return prompts.SO_FAR.format(summary="\n".join(parts))

    def _assemble(
        self,
        brief: LessonBrief,
        sections: list[Any],
        exercises: list[Any],
        title_en: str,
        content_version: int,
        job_id: int | None,
    ) -> Lesson:
        minutes = min(90, max(5, round(5 + 2 * len(sections) + 1.5 * len(exercises))))
        lesson = Lesson(
            id=brief.outline.id,
            content_version=content_version,
            level=brief.level,
            unit=brief.unit_id,
            title=brief.outline.title,
            title_en=title_en,
            objectives=list(brief.outline.objectives),
            grammar_topics=list(brief.outline.grammar_topics),
            estimated_minutes=minutes,
            sections=sections,
            exercises=exercises,
        )
        # Tidy before hashing: the generated hash must match the content as written.
        lesson = Lesson.model_validate(tidy(lesson.model_dump(mode="json", exclude_none=True)))
        provenance = Provenance(
            generator=f"llm/{self.chat.model}",
            prompts=dict(prompts.PROMPT_VERSIONS),
            generated_at=datetime.now(UTC),
            generated_hash=content_hash(lesson),
            job_id=job_id,
        )
        return lesson.model_copy(update={"provenance": provenance})


class LessonReviser:
    """Revise selected parts of a lesson according to reviewer notes, one item per call."""

    def __init__(
        self,
        chat: ChatModel,
        ref: Reference,
        progress: Progress | None = None,
        *,
        critic: bool = True,
    ) -> None:
        self.chat, self.ref = chat, ref
        self.progress = progress or (lambda message: None)
        self.critic = critic
        self.stats = Stats()

    def revise(
        self,
        base: dict[str, Any],
        notes: str,
        targets: list[str],
        *,
        content_version: int,
        job_id: int | None,
    ) -> GenerationResult:
        """Revise a lesson given as plain data. The base need not satisfy today's schema rules:
        invalid items are revised too, with their validation error added to the notes."""
        ids = [item["id"] for item in [*base["sections"], *base["exercises"]]]
        wanted = set(targets) or set(ids)
        self.dropped: list[Issue] = []
        sections = [
            _clean_vocab(self._item(d, SECTION_TYPES, notes, d["id"] in wanted))
            for d in base["sections"]
        ]
        exercises = [
            item
            for d in base["exercises"]
            if (item := self._item(d, EXERCISE_TYPES, notes, d["id"] in wanted, droppable=True))
        ]
        revised = self._build(base, sections, exercises, content_version)
        # One repair round, as in generation: the revision must pass the deterministic checks.
        broken = self._item_errors(revised)
        if broken:
            self.stats.repairs += 1
            self.progress(f"Repairing: {'; '.join(m for ms in broken.values() for m in ms)[:200]}")
            sections = [_clean_vocab(self._repair(x, SECTION_TYPES, broken)) for x in sections]
            exercises = [self._repair(x, EXERCISE_TYPES, broken) for x in exercises]
            repaired = self._build(base, sections, exercises, content_version)
            if len(self._item_errors(repaired)) < len(broken):
                revised = repaired
        provenance = Provenance(
            generator=f"llm/{self.chat.model}",
            prompts=dict(prompts.PROMPT_VERSIONS),
            generated_at=datetime.now(UTC),
            generated_hash=content_hash(revised),
            job_id=job_id,
        )
        revised = revised.model_copy(update={"provenance": provenance})
        issues = [*self.dropped, *check_lesson_quality(revised, self.ref)]
        if self.critic:
            self.progress("AI critic: proof-reading graded French sentences")
            issues += critique(self.chat, revised, self.stats.record)
        return GenerationResult(revised, issues, self.stats)

    @staticmethod
    def _build(
        base: dict[str, Any], sections: list[Any], exercises: list[Any], content_version: int
    ) -> Lesson:
        topics = list(base.get("grammar_topics", []))
        exercises = [
            e if e.grammar_topics or not topics else e.model_copy(update={"grammar_topics": topics})
            for e in exercises
        ]
        data = {
            **{k: v for k, v in base.items() if k != "provenance"},
            "content_version": content_version,
            "sections": [s.model_dump(mode="json", exclude_none=True) for s in sections],
            "exercises": [e.model_dump(mode="json", exclude_none=True) for e in exercises],
        }
        return Lesson.model_validate(tidy(data))

    def _item_errors(self, lesson: Lesson) -> dict[str, list[str]]:
        """Deterministic errors by item id ("ex-07.hint" belongs to "ex-07")."""
        found: dict[str, list[str]] = {}
        for issue in check_lesson_quality(lesson, self.ref):
            if issue.severity == "error" and ":" in issue.path:
                item = issue.path.split(":", 1)[1].split(".", 1)[0]
                found.setdefault(item, []).append(issue.message)
        return found

    def _repair(
        self, item: Any, types: dict[str, type[BaseModel]], broken: dict[str, list[str]]
    ) -> Any:
        if item.id not in broken:
            return item
        problems = "\n".join(f"- {m}" for m in broken[item.id])
        try:
            return self._revise_item(
                types[item.type],
                item.model_dump(mode="json", exclude_none=True),
                prompts.REPAIR.format(problems=problems),
            )
        except InvalidOutput:
            return item

    def _item(
        self,
        data: dict[str, Any],
        types: dict[str, type[BaseModel]],
        notes: str,
        wanted: bool,
        *,
        droppable: bool = False,
    ) -> Any:
        model = types[data["type"]]
        if not wanted:
            try:
                return model.model_validate(data)
            except ValidationError as exc:
                notes = f"{notes}\nThis item is currently invalid: {exc.errors()[0]['msg']}"
        try:
            return self._revise_item(model, data, notes)
        except InvalidOutput as exc:
            if not droppable:
                raise
            # Like generation: one stubborn exercise should not sink the revision.
            self.dropped.append(
                Issue("warning", data["id"], f"dropped after failed revision: {exc}")
            )
            return None

    def _revise_item(self, model: type[BaseModel], data: dict[str, Any], notes: str) -> BaseModel:
        self.progress(f"Revising {data['id']}")
        if data["type"] in DRAFT_SHAPES:
            return self._revise_vocab_section(model, data, notes)
        current = json.dumps(data, ensure_ascii=False, indent=1)
        messages = [
            Message("system", prompts.SYSTEM),
            Message("user", prompts.REVISE.format(notes=notes, current=current)),
        ]
        started = time.perf_counter()
        revised, completion = complete_structured(self.chat, messages, model, max_tokens=MAX_TOKENS)
        self.stats.record(time.perf_counter() - started, completion.completion_tokens or 0)
        # Identity and curriculum metadata are not the LLM's to change.
        keep: dict[str, Any] = {
            k: data[k] for k in ("id", "type", "grammar_topics", "reading_id") if k in data
        }
        return revised.model_copy(update=keep)

    def _revise_vocab_section(
        self, model: type[BaseModel], data: dict[str, Any], notes: str
    ) -> BaseModel:
        """Reading/vocabulary sections are revised in the gender-required draft shape, then
        converted back with the same deterministic clean-up as generation."""
        draft_model, list_key = DRAFT_SHAPES[data["type"]]
        items = [VocabItem.model_validate(i) for i in data.get(list_key, [])]
        current = json.dumps(
            {**data, list_key: [as_draft(i) for i in items]}, ensure_ascii=False, indent=1
        )
        messages = [
            Message("system", prompts.SYSTEM),
            Message("user", prompts.REVISE.format(notes=notes, current=current)),
        ]
        started = time.perf_counter()
        revised, completion = complete_structured(
            self.chat, messages, draft_model, max_tokens=MAX_TOKENS
        )
        self.stats.record(time.perf_counter() - started, completion.completion_tokens or 0)
        out = revised.model_dump()
        out[list_key] = [vocab_item(d) for d in getattr(revised, list_key)]
        out.update(id=data["id"], type=data["type"])
        return model.model_validate(out)


def _clean_vocab(section: Any) -> Any:
    if isinstance(section, VocabularySection):
        return section.model_copy(update={"items": [strip_article(i) for i in section.items]})
    if isinstance(section, ReadingSection):
        return section.model_copy(update={"glossary": [strip_article(i) for i in section.glossary]})
    return section
