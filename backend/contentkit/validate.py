"""Repository loading and validation: schema errors, referential integrity, and deterministic
quality checks. Errors block import/publication; warnings are shown during review."""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ValidationError

from .models import (
    BLANK,
    CurriculumLevel,
    ExamplesSection,
    FillBlankExercise,
    GrammarTopicRegistry,
    Lesson,
    LessonOutline,
    ReadingSection,
    RegionalNoteSection,
    TranslateExercise,
    VocabularySection,
)
from .reference import Reference, normalize
from .yamlio import load_yaml

Severity = Literal["error", "warning"]
AddFn = Callable[[Severity, str, str], None]


@dataclass(frozen=True)
class Issue:
    severity: Severity
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.severity.upper():7s} {self.path}: {self.message}"


@dataclass
class Repository:
    root: Path
    levels: dict[str, CurriculumLevel] = field(default_factory=dict)
    topics: GrammarTopicRegistry | None = None
    lessons: dict[str, tuple[Path, Lesson]] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)

    @property
    def outlines(self) -> dict[str, tuple[str, str, LessonOutline]]:
        """lesson id -> (level, unit id, outline), in curriculum order."""
        return {
            lesson.id: (level.level, unit.id, lesson)
            for level in self.levels.values()
            for unit in level.units
            for lesson in unit.lessons
        }

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]


def _parse[T: BaseModel](model: type[T], path: Path, root: Path, issues: list[Issue]) -> T | None:
    rel = str(path.relative_to(root))
    try:
        return model.model_validate(load_yaml(path))
    except ValidationError as exc:
        for err in exc.errors():
            loc = ".".join(str(p) for p in err["loc"])
            issues.append(Issue("error", f"{rel}:{loc}", err["msg"]))
    except Exception as exc:  # YAML syntax and IO errors
        issues.append(Issue("error", rel, f"cannot read: {exc}"))
    return None


def load_repository(root: Path) -> Repository:
    repo = Repository(root)
    for path in sorted((root / "curriculum").glob("*.yaml")):
        if level := _parse(CurriculumLevel, path, root, repo.issues):
            if path.stem != level.level.lower():
                repo.issues.append(
                    Issue("error", str(path.relative_to(root)), "file name must match level")
                )
            repo.levels[level.level] = level
    topics_path = root / "grammar" / "topics.yaml"
    if topics_path.exists():
        repo.topics = _parse(GrammarTopicRegistry, topics_path, root, repo.issues)
    for path in sorted((root / "lessons").glob("*/*.yaml")):
        if lesson := _parse(Lesson, path, root, repo.issues):
            repo.lessons[lesson.id] = (path, lesson)
    check_references(repo)
    return repo


def check_references(repo: Repository) -> None:
    add = repo.issues.append
    topic_ids = {t.id for t in repo.topics.topics} if repo.topics else set()
    outlines = repo.outlines
    order = {lesson_id: i for i, lesson_id in enumerate(outlines)}

    for lesson_id, (level, _unit, outline) in outlines.items():
        where = f"curriculum/{level.lower()}.yaml:{lesson_id}"
        for topic in outline.grammar_topics:
            if topic not in topic_ids:
                add(Issue("error", where, f"unknown grammar topic {topic!r}"))
        for prereq in outline.prerequisites:
            if prereq not in order:
                add(Issue("error", where, f"unknown prerequisite {prereq!r}"))
            elif order[prereq] > order[lesson_id]:
                add(
                    Issue(
                        "warning", where, f"prerequisite {prereq!r} comes later in the curriculum"
                    )
                )

    for lesson_id, (path, lesson) in repo.lessons.items():
        rel = str(path.relative_to(repo.root))
        if path.stem != lesson_id:
            add(Issue("error", rel, f"file name must be {lesson_id}.yaml"))
        if path.parent.name != lesson.level.lower():
            add(Issue("error", rel, f"must live in lessons/{lesson.level.lower()}/"))
        if lesson_id not in outlines:
            add(Issue("error", rel, "lesson is not in any curriculum outline"))
        else:
            level, unit, _ = outlines[lesson_id]
            if (lesson.level, lesson.unit) != (level, unit):
                add(Issue("error", rel, f"outline places this lesson in {level}/{unit}"))
        used = list(lesson.grammar_topics) + [t for e in lesson.exercises for t in e.grammar_topics]
        for topic in sorted(set(used) - topic_ids):
            add(Issue("error", rel, f"unknown grammar topic {topic!r}"))


# --- Deterministic quality checks ----------------------------------------------------------

_ARTICLE = re.compile(r"^(le|la|les|un|une|des)\s|^l'", re.IGNORECASE)
_ENGLISH = re.compile(r"\b(the|and|is|are|of|to|you|with|this|that|it)\b", re.IGNORECASE)
_WORD = re.compile(r"[\w'’-]+")


def _looks_english(text: str) -> bool:
    words = _WORD.findall(text)
    return len(words) >= 4 and len(_ENGLISH.findall(text)) / len(words) > 0.2


def check_lesson_quality(lesson: Lesson, ref: Reference) -> list[Issue]:
    issues: list[Issue] = []

    def add(severity: Severity, where: str, message: str) -> None:
        issues.append(Issue(severity, f"{lesson.id}:{where}", message))

    for section in lesson.sections:
        if isinstance(section, VocabularySection | ReadingSection):
            items = section.items if isinstance(section, VocabularySection) else section.glossary
            for item in items:
                if _ARTICLE.match(item.fr):
                    add(
                        "warning",
                        section.id,
                        f"write {item.fr!r} without its article (gender is a field)",
                    )
                if item.pos == "noun" and item.gender and ref.nouns:
                    expected = ref.noun_gender(item.fr)
                    if expected in ("m", "f") and expected != item.gender:
                        add(
                            "error",
                            section.id,
                            f"{item.fr!r} is {expected}, not {item.gender} (Lexique)",
                        )
                if item.region == "qc":
                    _check_quebec(add, section.id, item.fr, ref)
        if isinstance(section, ExamplesSection):
            for example in section.examples:
                if _looks_english(example.fr):
                    add("warning", section.id, f"French example looks English: {example.fr!r}")
        if isinstance(section, ReadingSection) and _looks_english(section.passage_fr):
            add("error", section.id, "reading passage does not look French")
        if isinstance(section, RegionalNoteSection):
            for variant in section.variants:
                _check_quebec(add, section.id, variant.qc, ref)

    for ex in lesson.exercises:
        if isinstance(ex, FillBlankExercise):
            _check_fill_blank(add, ex, ref)
        if isinstance(ex, TranslateExercise):
            answers_english = [_looks_english(a) for a in ex.accepted_answers]
            if ex.direction == "en_fr" and any(answers_english):
                add("error", ex.id, "en_fr answers must be French")
            if ex.direction == "fr_en" and _looks_english(ex.prompt):
                add("error", ex.id, "fr_en prompt must be French")
    return issues


def _check_quebec(add: AddFn, where: str, term: str, ref: Reference) -> None:
    if ref.quebec and not ref.quebec_terms_in(term):
        add("warning", where, f"Québec usage {term!r} is not in the verified lexicon; check it")


def _check_fill_blank(add: AddFn, ex: FillBlankExercise, ref: Reference) -> None:
    for answer in ex.answers:
        filled = normalize(ex.sentence.replace(BLANK, answer)).split()
        if any(a == b and len(a) > 2 for a, b in zip(filled, filled[1:], strict=False)):
            add("error", ex.id, f"word repeated after filling the blank with {answer!r}")
    infinitive = _hint_infinitive(ex.hint)
    if infinitive is None or not ref.verbs:
        return
    forms = ref.verb_forms(infinitive)
    if forms is None:
        add("warning", ex.id, f"verb {infinitive!r} is not in the conjugation reference")
        return
    for answer in ex.answers:
        if not _is_verb_form(normalize(answer), forms):
            add("error", ex.id, f"{answer!r} is not a form of {infinitive!r} in the reference")


def _hint_infinitive(hint: str | None) -> str | None:
    """Extract the infinitive from hints like "(aller)" or "aller"; None if not a verb hint."""
    if not hint:
        return None
    text = hint.strip().strip("()").strip()
    return (
        text if re.fullmatch(r"(se |s')?[a-zàâçéèêëîïôûùüÿœ-]+(er|ir|re|oir)", text, re.I) else None
    )


_PRONOUNS = re.compile(r"^(je |j'|tu |il |elle |on |nous |vous |ils |elles |qu'|que )+")


def _is_verb_form(answer: str, forms: set[str]) -> bool:
    """True if the answer, with or without a leading subject pronoun, is a reference form
    (the reference includes agreed participles: est allée, sont allées)."""
    return answer in forms or _PRONOUNS.sub("", answer) in forms


def validate_repository(root: Path, *, quality: bool = True) -> Repository:
    repo = load_repository(root)
    if quality:
        ref = Reference.load(root)
        if not ref.verbs or not ref.nouns:
            repo.issues.append(
                Issue("warning", "reference/", "reference data missing; some checks skipped")
            )
        for _path, lesson in repo.lessons.values():
            repo.issues.extend(check_lesson_quality(lesson, ref))
    return repo


def format_issues(issues: Iterable[Issue]) -> str:
    return "\n".join(str(i) for i in issues)
