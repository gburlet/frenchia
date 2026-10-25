"""Personalized practice (Phase 7): new exercises on a learner's weak grammar topic, written by
the local LLM around their recent mistakes and grounded in the published lesson that teaches it.

Nobody reviews these before the learner sees them, so the bar is stricter than for lessons:
every item must pass the lesson quality checks, and any item the AI critic flags is dropped
rather than reported. Plain Python on top of ChatModel/Reference, like the lesson generator."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from contentkit.models import (
    ExamplesSection,
    ExplanationSection,
    FillBlankExercise,
    Lesson,
    TableSection,
    TranslateExercise,
)
from contentkit.reference import Reference
from contentkit.validate import Issue
from inference.llm import ChatModel

from . import prompts
from .critic import critique
from .generation import LessonBrief, LessonGenerator, Progress, Stats

PLAN: tuple[tuple[str, int], ...] = (("fill_blank", 2), ("translate_en_fr", 2))
GROUNDING = (ExplanationSection, TableSection, ExamplesSection)
GRADED = (FillBlankExercise, TranslateExercise)


@dataclass
class PracticeResult:
    exercises: list[FillBlankExercise | TranslateExercise]
    dropped: list[Issue]
    stats: Stats


def _key(exercise: Any) -> str:
    text = exercise.sentence if isinstance(exercise, FillBlankExercise) else exercise.prompt
    return " ".join(text.casefold().split())


class PracticeGenerator(LessonGenerator):
    def __init__(self, chat: ChatModel, ref: Reference, progress: Progress | None = None) -> None:
        super().__init__(chat, ref, progress, critic=False)

    def practice(
        self, brief: LessonBrief, lesson: Lesson, topic: str, mistakes: Sequence[str]
    ) -> PracticeResult:
        """Exercises for `topic` in the style of `lesson`'s exercises (ids p-01, p-02...)."""
        context = self._context(brief) + prompts.PRACTICE.format(
            mistakes="\n".join(f"- {m}" for m in mistakes) or "- (none recorded: general practice)",
            level=brief.level,
        )
        sections = [s for s in lesson.sections if isinstance(s, GROUNDING)]
        seen = {_key(e) for e in lesson.exercises if isinstance(e, GRADED)}
        exercises: list[Any] = []
        for step, count in PLAN:
            self.progress(f"Writing {count} {step.replace('_', ' ')} exercises")
            for exercise in self._exercises(step, count, brief, context, sections):
                if _key(exercise) in seen:
                    self.dropped.append(
                        Issue("warning", exercise.id, "dropped: repeats a lesson exercise")
                    )
                    continue
                seen.add(_key(exercise))
                exercises.append(exercise)
        exercises = [
            e.model_copy(update={"id": f"p-{i:02d}", "grammar_topics": [topic]})
            for i, e in enumerate(exercises, 1)
        ]
        if exercises:
            self.progress("AI critic: proof-reading the answer keys")
            draft = lesson.model_copy(update={"exercises": exercises, "provenance": None})
            flagged = {
                issue.path.split(":", 1)[1]: issue
                for issue in critique(self.chat, draft, self.stats.record)
            }
            self.dropped += flagged.values()
            exercises = [e for e in exercises if e.id not in flagged]
        return PracticeResult(exercises, self.dropped, self.stats)
