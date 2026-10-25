"""Loading and deterministic checks for the Verb and Vocabulary Station content:
verb drill sets, per-verb context-sentence banks, vocabulary themes and themed sets."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from .conjugation import TENSE_BY_KEY, find_form, verb_slug
from .models import VerbBank, VerbSetRegistry, VocabEntry, VocabSet, VocabThemeRegistry
from .reference import Reference, normalize
from .validate import (
    _ARTICLE,
    _LATEX,
    FOREIGN_SCRIPT,
    Issue,
    Severity,
    _check_quebec,
    _looks_english,
    _parse,
)


@dataclass
class Banks:
    verb_sets: VerbSetRegistry | None = None
    verb_banks: dict[str, tuple[Path, VerbBank]] = field(default_factory=dict)
    vocab_themes: VocabThemeRegistry | None = None
    vocab_sets: dict[str, tuple[Path, VocabSet]] = field(default_factory=dict)
    issues: list[Issue] = field(default_factory=list)


def load_banks(root: Path) -> Banks:
    banks = Banks()
    if (path := root / "verbs" / "sets.yaml").exists():
        banks.verb_sets = _parse(VerbSetRegistry, path, root, banks.issues)
    for path in sorted((root / "verbs" / "bank").glob("*.yaml")):
        if bank := _parse(VerbBank, path, root, banks.issues):
            banks.verb_banks[bank.id] = (path, bank)
    if (path := root / "vocabulary" / "themes.yaml").exists():
        banks.vocab_themes = _parse(VocabThemeRegistry, path, root, banks.issues)
    for path in sorted((root / "vocabulary" / "sets").glob("*.yaml")):
        if vocab := _parse(VocabSet, path, root, banks.issues):
            banks.vocab_sets[vocab.id] = (path, vocab)
    return banks


def check_banks(banks: Banks, root: Path, ref: Reference) -> None:
    add = banks.issues.append
    if banks.verb_sets and ref.verbs:
        hidden = set(banks.verb_sets.hidden)
        for verb_set in banks.verb_sets.sets:
            for verb in verb_set.verbs:
                if verb not in ref.verbs:
                    add(Issue("error", f"verbs/sets.yaml:{verb_set.id}", f"unknown verb {verb!r}"))
                elif verb in hidden:
                    add(Issue("error", f"verbs/sets.yaml:{verb_set.id}", f"{verb!r} is hidden"))
    for bank_id, (path, bank) in banks.verb_banks.items():
        rel = str(path.relative_to(root))
        if path.stem != bank_id:
            add(Issue("error", rel, f"file name must be {bank_id}.yaml"))
        banks.issues.extend(check_verb_bank(bank, ref, rel))
    themes = {t.id: t for t in banks.vocab_themes.themes} if banks.vocab_themes else {}
    for set_id, (path, vocab) in banks.vocab_sets.items():
        rel = str(path.relative_to(root))
        if path.stem != set_id:
            add(Issue("error", rel, f"file name must be {set_id}.yaml"))
        if set_id not in themes:
            add(Issue("error", rel, "set is not in vocabulary/themes.yaml"))
        elif themes[set_id].level != vocab.level:
            add(Issue("error", rel, f"theme level is {themes[set_id].level}"))
        banks.issues.extend(check_vocab_set(vocab, ref, rel))


_SUBJECT = {
    "je": r"\b(je|j'|j’)",
    "tu": r"\btu\b",
    "nous": r"\bnous\b",
    "vous": r"\bvous\b",
}


def _is_gloss(en: str, gloss: str) -> bool:
    """« Choose » or « to like, to love » where a sentence translation belongs."""
    words = re.findall(r"[\w']+", en.casefold())
    glosses = {g.strip().removeprefix("to ").strip() for g in gloss.casefold().split(",")}
    bare = " ".join(w for w in words if w != "to")
    return len(words) <= 2 or bare in glosses or normalize(en) == normalize(gloss)


def check_verb_bank(bank: VerbBank, ref: Reference, where: str) -> list[Issue]:
    issues: list[Issue] = []

    def add(severity: Severity, at: str, message: str) -> None:
        issues.append(Issue(severity, f"{where}:{at}", message))

    if ref.verbs and bank.infinitive not in ref.verbs:
        add("error", "infinitive", f"{bank.infinitive!r} is not in the conjugation reference")
        return issues
    if bank.id != verb_slug(bank.infinitive):
        add("error", "id", f"id must be {verb_slug(bank.infinitive)!r}")
    # A Québec verb (magasiner, jaser) makes every sentence Québec usage, whatever the form.
    quebec_verb = ref.is_quebec_word(bank.infinitive)
    seen: set[str] = set()
    for i, s in enumerate(bank.sentences):
        at = f"sentences.{i}"
        if normalize(s.fr) in seen:
            add("error", at, "duplicate sentence")
        seen.add(normalize(s.fr))
        if s.tense.startswith("imperatif") and s.person not in ("tu", "nous", "vous"):
            add("error", at, "the imperative only has tu, nous and vous")
            continue
        if ref.verbs:
            found = find_form(ref, bank.infinitive, s.tense, s.person, s.fr)
            label = TENSE_BY_KEY[s.tense].label
            if found is None:
                add("error", at, f"no {label} « {s.person} » form of {bank.infinitive} in {s.fr!r}")
            elif normalize(found) != normalize(s.form):
                add("error", at, f"form should be {found!r} (as written in the sentence)")
        if s.person in _SUBJECT and not s.tense.startswith("imperatif"):
            if not re.search(_SUBJECT[s.person], s.fr, re.IGNORECASE):
                add("warning", at, f"no « {s.person} » subject in the sentence")
        if _looks_english(s.fr):
            add("error", at, "sentence does not look French")
        if _is_gloss(s.en, bank.en):
            add("error", at, f"the English {s.en!r} is not a translation of the sentence")
        elif re.search(r"«|\d+\.\s+\w+ \(", s.en):
            add("error", at, "the English runs on into other text")
        if s.region == "qc" and not quebec_verb:
            _check_quebec(add, at, s.fr, ref)
        for text in (s.fr, s.en):
            if _LATEX.search(text):
                add("warning", at, "LaTeX markup in text")
            if FOREIGN_SCRIPT.search(text):
                add("error", at, "text contains another script")
    if FOREIGN_SCRIPT.search(f"{bank.en} {bank.note or ''}"):
        add("error", "en", "gloss or note contains another script")
    return issues


def check_vocab_set(vocab: VocabSet, ref: Reference, where: str) -> list[Issue]:
    issues: list[Issue] = []
    seen: set[str] = set()
    for entry in vocab.entries:
        key = normalize(entry.fr)
        if key in seen:
            issues.append(Issue("error", f"{where}:{entry.id}", f"duplicate word {entry.fr!r}"))
        seen.add(key)
        issues += check_vocab_entry(entry, ref, where)
    return issues


def check_vocab_entry(entry: VocabEntry, ref: Reference, where: str) -> list[Issue]:
    issues: list[Issue] = []

    def add(severity: Severity, at: str, message: str) -> None:
        issues.append(Issue(severity, f"{where}:{at}", message))

    if _ARTICLE.match(entry.fr):
        add("error", entry.id, f"write {entry.fr!r} without its article (gender is a field)")
    if entry.pos == "noun" and entry.gender and ref.nouns:
        expected = ref.noun_gender(entry.fr)
        if expected in ("m", "f") and expected != entry.gender:
            add("error", entry.id, f"{entry.fr!r} is {expected}, not {entry.gender} (Lexique)")
    if entry.region == "qc":
        _check_quebec(add, entry.id, entry.fr, ref)
    if not uses_word(entry.fr, entry.example_fr):
        add("warning", entry.id, f"the example does not seem to use {entry.fr!r}")
    if _looks_english(entry.example_fr):
        add("error", entry.id, "example does not look French")
    for text in (entry.fr, entry.en, entry.example_fr, entry.example_en, entry.note or ""):
        if _LATEX.search(text):
            add("warning", entry.id, "LaTeX markup in text")
        if FOREIGN_SCRIPT.search(text):
            add("error", entry.id, "text contains another script")
    return issues


def uses_word(word: str, sentence: str) -> bool:
    """Loose check that a sentence contains a word or an inflection of it (stem match on each
    content word: cheval/chevaux, aller/allons is beyond it, hence a warning only)."""
    text = normalize(sentence)
    parts = [p for p in normalize(word).replace("'", " ").replace("-", " ").split() if len(p) > 2]
    for part in parts or normalize(word).split():
        stem = part[: max(3, len(part) - 3)]
        if stem not in text:
            return False
    return True
