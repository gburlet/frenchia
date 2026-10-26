"""Repository loading and validation: schema errors, referential integrity, and deterministic
quality checks. Errors block import/publication; warnings are shown during review."""

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ValidationError

from .models import (
    BLANK,
    ComprehensionExercise,
    CurriculumLevel,
    ExamplesSection,
    FillBlankExercise,
    GrammarTopicRegistry,
    Lesson,
    LessonOutline,
    MultipleChoiceExercise,
    ReadingSection,
    RegionalNoteSection,
    TranslateExercise,
    VocabularySection,
)
from .reference import Reference, normalize
from .yamlio import load_yaml

if TYPE_CHECKING:
    from .banks import Banks

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
    banks: "Banks | None" = None

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

# « … », "…" or '…' quotations (≥ 3 words are checked against the passage)
_QUOTE = re.compile(r"«\s*([^»]+?)\s*»|\"([^\"]+)\"|(?<![\w])'([^']{12,}?)'(?![\w])")
_LATEX = re.compile(r"\$\\[a-zA-Z]+\$|\\(?:rightarrow|leftarrow|to|times|cdot)\b")


def _strings(value: object, path: str = "") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(path or "lesson", value)]
    if isinstance(value, list):
        return [item for i, v in enumerate(value) for item in _strings(v, f"{path}.{i}")]
    if isinstance(value, dict):
        return [
            item for k, v in value.items() for item in _strings(v, f"{path}.{k}" if path else k)
        ]
    return []


_ARTICLE = re.compile(r"^(le|la|les|un|une|des)\s|^l'", re.IGNORECASE)
# Small models occasionally emit tokens from other scripts (CJK, Cyrillic...) mid-sentence.
FOREIGN_SCRIPT = re.compile(
    r"[\u0370-\u03ff\u0400-\u04ff\u0590-\u06ff\u0900-\u0dff\u0e00-\u0e7f"
    r"\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\uf900-\ufaff]"
)
_ENGLISH = re.compile(r"\b(the|and|is|are|of|to|you|with|this|that|it)\b", re.IGNORECASE)
_WORD = re.compile(r"[\w'’-]+")


def _looks_english(text: str) -> bool:
    words = _WORD.findall(text)
    return len(words) >= 4 and len(_ENGLISH.findall(text)) / len(words) > 0.2


UNVERIFIED_QUEBEC = "is not in the verified lexicon"
# The course uses standard language only (prompts.SYSTEM): no vulgarity or sacres.
_VULGAR = re.compile(
    r"\b(cul|merde|chier|foutre|putain|salope|tabarnak|tabarnac|tabarouette|câlisse|calisse|"
    r"crisse|ostie|osti|hostie|ciboire|sacrament)\b",
    re.I,
)

# Exercise text is shown without formatting, so a question about "the underlined words" is
# unanswerable (Gemma writes these).
_FORMATTING_REF = re.compile(
    r"\b(underlined|in bold|bolded|in italics|soulign[ée]e?s?|en gras|en italique)\b|~~", re.I
)
_BOLD = re.compile(r"\*\*")  # rendered only in explanations
HINT_MAX = 160
# « parce que il », « si il », « je ai »: elision is never optional in written French.
_NO_ELISION = re.compile(
    r"\b(?:(?:parce |lors|puis|jus)?que (?:il|ils|elle|elles|on|un|une)|si (?:il|ils)|"
    r"je (?:ai|avais|aurai|étais|aime|habite|en|y))\b",
    re.I,
)
# Québec usage (prompts.SYSTEM): « la fin de semaine », not « le week-end », except when the
# text is comparing with France.
_WEEK_END = re.compile(r"\b(?:le |ce |du |au |en )?week-?ends?\b", re.I)
_ABOUT_FRANCE = re.compile(r"\bFrance\b|\beurop", re.I)
_FRENCH_FIELDS = {"fr", "passage_fr", "example_fr", "sentence", "answers"}
# « loin du le centre-ville », « grâce au le beau temps » (a filled blank or an answer key).
# « loin de le centre-ville »: after a compound preposition de + le/les must contract. (Before a
# verb « de le » is a pronoun and correct: « essayer de le faire ».)
_NO_CONTRACTION = re.compile(
    r"\b(?:près|loin|à côté|en face|autour|au lieu|à cause|au bord|au milieu|le long) de "
    r"(?:le|les)\b",
    re.I,
)
_DOUBLE_ARTICLE = re.compile(r"\b(du|au|aux) (?:(le|la|les)\b|l['’])", re.I)
# Bits of the generation prompt that reach the learner (« no slang that isn't in the verified
# list »).
_PROMPT_LEAK = re.compile(
    r"verified (list|lexicon|usage)|\bthe lexicon\b|\bJSON\b|≤\s*\d+ char", re.I
)


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
        if not isinstance(section, ReadingSection):  # a whole passage names many meals
            _check_meal_pairs(add, section.id, _section_meal_pairs(section))
        if isinstance(section, RegionalNoteSection):
            for variant in section.variants:
                _check_quebec(add, section.id, variant.qc, ref)

    for path, text in _strings(lesson.model_dump(mode="json", exclude={"provenance"})):
        # Wrong options are deliberately wrong; the right one is checked with the answer keys.
        if ".options." not in path and (m := _NO_ELISION.search(text)):
            add("error", path, f"missing elision: « {m.group(0)} »")
        parts = path.split(".")
        field = next((p for p in reversed(parts) if not p.isdigit()), "")
        # Regional-note variants hold the France form in "fr" on purpose.
        french = "variants" not in parts and field in _FRENCH_FIELDS
        if french and (m := _WEEK_END.search(text)) and not _ABOUT_FRANCE.search(text):
            add("error", path, f"« {m.group(0)} »: Québec usage is « la fin de semaine »")
        if FOREIGN_SCRIPT.search(text):
            add("error", path, f"text contains another script: {text[:60]!r}")
        if _VULGAR.search(text):
            add("error", path, f"vulgar or swear word {_VULGAR.search(text).group(0)!r}")  # type: ignore[union-attr]
        if _LATEX.search(text):
            add("warning", path, f"LaTeX markup in text: {_LATEX.search(text).group(0)!r}")  # type: ignore[union-attr]

    passages = {
        s.id: normalize(s.passage_fr) for s in lesson.sections if isinstance(s, ReadingSection)
    }
    seen: dict[str, str] = {}
    for ex in lesson.exercises:
        hint = getattr(ex, "hint", None)
        if hint and (len(hint) > HINT_MAX or "\n" in hint.strip()):
            add("error", ex.id, f"the hint must be one short line (≤{HINT_MAX} characters)")
        text = next(getattr(ex, f) for f in ("sentence", "prompt", "question") if hasattr(ex, f))
        stem = normalize(text).strip(" ?.!")
        if stem in seen:
            add("error", ex.id, f"repeats {seen[stem]}")
        seen.setdefault(stem, ex.id)
        for path, text in _strings(ex.model_dump(mode="json")):
            if _PROMPT_LEAK.search(text):
                add("error", f"{ex.id}.{path}", "text mentions the generation instructions")
            if _FORMATTING_REF.search(text) or (
                _BOLD.search(text) and not path.endswith("explanation")
            ):
                add(
                    "error",
                    f"{ex.id}.{path}",
                    "exercises are plain text: nothing is underlined or bold",
                )
        if isinstance(ex, ComprehensionExercise) and ex.reading_id in passages:
            for quote in _QUOTE.findall(ex.explanation):
                text = next(q for q in quote if q)
                if (
                    len(text.split()) >= 3
                    and normalize(text).strip(" .!?…") not in passages[ex.reading_id]
                ):
                    add(
                        "error",
                        ex.id,
                        f"explanation quotes text that is not in the reading: {text!r}",
                    )
        answers = [*getattr(ex, "answers", []), *getattr(ex, "accepted_answers", [])]
        if any("(" in a or "[" in a or "//" in a for a in answers):
            add("error", ex.id, "an accepted answer is a full answer, with no notes in brackets")
        for text in _graded_french(ex):
            if m := _NO_ELISION.search(text):  # a filled blank: « ___ il » + « parce que »
                add("error", ex.id, f"missing elision once filled: « {m.group(0)} »")
            if (m := _WEEK_END.search(text)) and not _ABOUT_FRANCE.search(text):
                add("error", ex.id, f"« {m.group(0)} »: Québec usage is « la fin de semaine »")
            if m := _NO_CONTRACTION.search(text):
                add("error", ex.id, f"« {m.group(0)} »: de + le/les contract (du/des)")
            if m := _DOUBLE_ARTICLE.search(text):
                add("error", ex.id, f"« {m.group(0)} »: du/au/aux already contain the article")
            for word in _unknown_words(text, ref):
                add("error", ex.id, f"{word!r} is not a French word (not in Lexique)")
        if isinstance(ex, FillBlankExercise):
            _check_fill_blank(add, ex, ref)
        if isinstance(ex, TranslateExercise):
            _check_meals(add, ex)
            answers_english = [_looks_english(a) for a in ex.accepted_answers]
            if ex.direction == "en_fr" and any(answers_english):
                add("error", ex.id, "en_fr answers must be French")
            if ex.direction == "fr_en" and _looks_english(ex.prompt):
                add("error", ex.id, "fr_en prompt must be French")
    return issues


def _check_quebec(add: AddFn, where: str, term: str, ref: Reference) -> None:
    if ref.quebec and not ref.quebec_terms_in(term):
        add("warning", where, f"Québec usage {term!r} {UNVERIFIED_QUEBEC}; check it")


def _check_fill_blank(add: AddFn, ex: FillBlankExercise, ref: Reference) -> None:
    for answer in ex.answers:
        # Split at apostrophes too: « parce qu'il il était » repeats « il ».
        # Inline hints (« décidé ___ (partir) ») are not part of the sentence.
        sentence = re.sub(r"\([^)]*\)", " ", ex.sentence.replace(BLANK, answer))
        filled = re.findall(r"[^\W\d_]+", normalize(sentence))
        if any(
            a == b and a not in _REFLEXIVE_DOUBLES and len(a) > 1  # « où où », « il il »
            for a, b in zip(filled, filled[1:], strict=False)
        ):
            add("error", ex.id, f"word repeated after filling the blank with {answer!r}")
    hint_words = f" {_words(ex.hint or '')} "
    for answer in ex.answers:
        if f" {_words(answer)} " in hint_words:
            add("error", ex.id, f"the hint gives away the answer {answer!r}")
    if ex.hint and ex.hint.strip() in ex.sentence:
        add("warning", ex.id, f"the hint {ex.hint.strip()!r} is also written inside the sentence")
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


def _words(text: str) -> str:
    """Normalized words without surrounding quotes: « 'le' » is the word « le »."""
    return " ".join(w.strip("'’-") for w in _WORD.findall(normalize(text)))


_TOKEN = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*")


def _unknown_words(text: str, ref: Reference) -> list[str]:
    """Words in French text that no dictionary knows (« bonned »). Capitalised words are
    skipped as likely names; hyphenated words pass if the whole or every part is known.
    Text that is mostly unknown words is English (« To be scared or nervous »), not French."""
    unknown = []
    tokens = [t for t in _TOKEN.findall(text) if len(t) >= 3 and not t[0].isupper()]
    for token in tokens:
        if ref.is_word(token):
            continue
        # « aujourd'hui » is one word; « l'épicerie », « est-ce » are known parts.
        parts = re.split(r"['’-]", token)
        if len(parts) > 1 and all(len(p) < 3 or ref.is_word(p) for p in parts):
            continue
        unknown.append(token)
    if _looks_english(text) or len(unknown) * 2 > len(tokens):
        return []
    return unknown


# Québec meal names (déjeuner = breakfast, dîner = lunch, souper = supper): the model keeps
# translating "dinner" as « dîner » and "lunch" as « déjeuner », as in France.
# Each rule: (English meal, French word that is not that meal, the meal it really is). A
# sentence naming both meals (« Le souper est meilleur que le dîner ») is fine.
_MEAL_CLASHES = [
    (
        re.compile(r"\b(dinner|supper)s?\b", re.I),
        re.compile(r"\bd[iî]n(er|é|ons|ez|ent)\b", re.I),
        re.compile(r"\blunch", re.I),
    ),
    (
        re.compile(r"\blunch", re.I),
        re.compile(r"(?<!petit-)(?<!petit )\bd[ée]jeun", re.I),
        re.compile(r"\bbreakfast", re.I),
    ),
]


def _check_meals(add: AddFn, ex: TranslateExercise) -> None:
    pairs = (
        [(ex.prompt, a) for a in ex.accepted_answers]
        if ex.direction == "en_fr"
        else [(a, ex.prompt) for a in ex.accepted_answers]
    )
    _check_meal_pairs(add, ex.id, pairs)


def _section_meal_pairs(section: object) -> list[tuple[str, str]]:
    """(English, French) pairs in examples, vocabulary, glossaries and the reading."""
    pairs: list[tuple[str, str]] = []
    if isinstance(section, ExamplesSection):
        pairs += [(e.en, e.fr) for e in section.examples]
    items = (
        section.items
        if isinstance(section, VocabularySection)
        else section.glossary
        if isinstance(section, ReadingSection)
        else []
    )
    for item in items:
        pairs.append((item.en, item.fr))
        if item.example_fr and item.example_en:
            pairs.append((item.example_en, item.example_fr))
    if isinstance(section, ReadingSection):
        pairs.append((section.translation_en, section.passage_fr))
    return pairs


def _check_meal_pairs(add: AddFn, where: str, pairs: list[tuple[str, str]]) -> None:
    for english, french in pairs:
        for en, fr, really in _MEAL_CLASHES:
            if en.search(english) and fr.search(french) and not really.search(english):
                add(
                    "error",
                    where,
                    f"Québec meals: « {fr.search(french).group(0)} » is not "  # type: ignore[union-attr]
                    f"{en.search(english).group(0)!r} (déjeuner = breakfast, dîner = lunch, "  # type: ignore[union-attr]
                    "souper = supper)",
                )
                return


def _graded_french(ex: object) -> list[str]:
    """French text a learner is graded against."""
    if isinstance(ex, FillBlankExercise):
        return [ex.sentence.replace(BLANK, a) for a in ex.answers]
    if isinstance(ex, TranslateExercise):
        return list(ex.accepted_answers) if ex.direction == "en_fr" else [ex.prompt]
    if isinstance(ex, MultipleChoiceExercise | ComprehensionExercise):
        # Only the right answer: wrong options are often deliberately wrong forms (« j'ai finé »).
        return [ex.options[ex.answer_index]]
    return []


def _hint_infinitive(hint: str | None) -> str | None:
    """Extract the infinitive from hints like "(aller)" or "aller"; None if not a verb hint."""
    if not hint:
        return None
    text = hint.strip().strip("()").strip()
    return (
        text if re.fullmatch(r"(se |s')?[a-zàâçéèêëîïôûùüÿœ-]+(er|ir|re|oir)", text, re.I) else None
    )


_PRONOUNS = re.compile(r"^(je |j'|tu |il |elle |on |nous |vous |ils |elles |qu'|que )+")


_REFLEXIVE_DOUBLES = {"nous", "vous"}  # « nous nous levons »


def _is_verb_form(answer: str, forms: set[str]) -> bool:
    """True if the answer, with or without a leading subject pronoun, is a reference form
    (the reference includes agreed participles: est allée, sont allées). A gérondif
    (« en jouant ») is « en » + the present participle."""
    bare = _PRONOUNS.sub("", answer)
    return answer in forms or bare in forms or bare.removeprefix("en ") in forms


def validate_repository(root: Path, *, quality: bool = True) -> Repository:
    from .banks import check_banks, load_banks  # banks builds on this module

    repo = load_repository(root)
    repo.banks = load_banks(root)
    if quality:
        ref = Reference.load(root)
        if not ref.verbs or not ref.nouns:
            repo.issues.append(
                Issue("warning", "reference/", "reference data missing; some checks skipped")
            )
        for _path, lesson in repo.lessons.values():
            repo.issues.extend(check_lesson_quality(lesson, ref))
        check_banks(repo.banks, root, ref)
    repo.issues.extend(repo.banks.issues)
    return repo


def format_issues(issues: Iterable[Issue]) -> str:
    return "\n".join(str(i) for i in issues)
