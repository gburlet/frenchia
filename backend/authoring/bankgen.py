"""Generation of the Verb and Vocabulary Station banks with the local LLM.

Verb banks: the reference supplies the exact form for each (tense, person) slot and the model
only writes a sentence around it, so it never has to conjugate. Every sentence is then checked
against the reference (the form must be present, with valid agreement) and dropped if it fails
after one repair round.

Vocabulary sets: one call lists the words, then examples are written in small batches. Noun
genders are corrected from Lexique, unverified Québec claims are downgraded, and items that
still fail the checks are dropped.

Plain Python on top of ChatModel/Reference: no Django, so it is testable with fakes."""

import random
import re
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from contentkit.banks import check_verb_bank, check_vocab_entry, check_vocab_set, uses_word
from contentkit.conjugation import (
    PERSONS,
    SUBJECT_LABELS,
    TENSE_BY_KEY,
    find_form,
    forms_for,
    verb_slug,
)
from contentkit.models import (
    Provenance,
    VerbBank,
    VerbSentence,
    VocabEntry,
    VocabSet,
    VocabTheme,
)
from contentkit.reference import Reference, normalize
from contentkit.validate import Issue
from contentkit.yamlio import content_hash
from inference.llm import ChatModel, Message, complete_structured

from . import prompts
from .generation import Stats
from .schemas import _ARTICLE, _ARTICLE_GENDER, tidy

BASE_SLOTS = (
    "indicatif.present",
    "indicatif.present",
    "indicatif.passe_compose",
    "indicatif.passe_compose",
    "indicatif.imparfait",
    "indicatif.futur_proche",
    "indicatif.futur_simple",
    "conditionnel.present",
    "subjonctif.present",
    "imperatif.present",
)
NO_IMPERATIVE = {"pouvoir", "devoir", "vouloir", "valoir", "savoir", "falloir", "naître"}
MAX_TOKENS = 1800
EXAMPLE_BATCH = 8
WORD_BATCH = 12


# --- LLM-facing schemas -------------------------------------------------------------------


class SentenceDraft(BaseModel):
    slot: int
    fr: str
    en: str = Field(description="English translation of the whole sentence")


class VerbBankDraft(BaseModel):
    sentences: list[SentenceDraft]
    gloss: str = Field(description="Only the verb's English gloss, e.g. 'to go'", max_length=60)
    note: str = Field(description="One English sentence, or empty", max_length=240)


class SentenceRepair(BaseModel):
    sentences: list[SentenceDraft]


class GlossDraft(BaseModel):
    en: str = Field(description="English gloss of the verb, e.g. 'to go'")


class WordDraft(BaseModel):
    fr: str = Field(description="The bare word or expression, without article")
    en: str
    pos: Literal["noun", "verb", "adjective", "adverb", "expression", "other"]
    gender: Literal["m", "f", "none"]
    region: Literal["qc", "common"]
    formality: Literal["formal", "standard", "familiar"]
    plural: str = Field(description="Irregular plural only (œil -> yeux), otherwise empty")


class WordList(BaseModel):
    entries: list[WordDraft]


class ExampleDraft(BaseModel):
    index: int
    example_fr: str
    example_en: str
    note: str


class ExampleList(BaseModel):
    items: list[ExampleDraft]


class EntryDraft(WordDraft):
    example_fr: str
    example_en: str
    note: str


# --- generator ------------------------------------------------------------------------------


class BankGenerator:
    def __init__(
        self,
        chat: ChatModel,
        ref: Reference,
        *,
        model_name: str = "",
        progress: Callable[[str], None] | None = None,
    ) -> None:
        self.chat = chat
        self.ref = ref
        self.model_name = model_name
        self.progress = progress or (lambda message: None)
        self.stats = Stats()

    # verb banks ----------------------------------------------------------------------------

    def slots(self, infinitive: str, extra_tenses: Sequence[str] = ()) -> list[tuple[str, str]]:
        """(tense, person) slots for a verb: a fixed A1-B1 spread plus any extra tenses."""
        rng = random.Random(infinitive)
        tenses = [
            t for t in BASE_SLOTS if not (t.startswith("imperatif") and _no_imperative(infinitive))
        ]
        tenses += [t for t in extra_tenses if t not in tenses and t in TENSE_BY_KEY]
        used: dict[str, set[str]] = {}
        slots = []
        for tense in tenses:
            persons = ["tu", "nous", "vous"] if tense.startswith("imperatif") else list(PERSONS)
            options = [p for p in persons if p not in used.get(tense, set())] or persons
            person = rng.choice(options)
            used.setdefault(tense, set()).add(person)
            slots.append((tense, person))
        return slots

    def verb_bank(
        self,
        infinitive: str,
        *,
        extra_tenses: Sequence[str] = (),
        version: int = 1,
    ) -> tuple[VerbBank, list[Issue]]:
        verb = self.ref.verbs[infinitive]
        slots = self.slots(infinitive, list(extra_tenses))
        lexicon = self._lexicon(infinitive)
        prompt = prompts.VERB_BANK.format(
            infinitive=infinitive,
            auxiliary=verb["auxiliary"],
            pronominal=", pronominal" if verb.get("pronominal") else "",
            lexicon=lexicon,
            slots="\n".join(
                self._slot_line(infinitive, i, t, p) for i, (t, p) in enumerate(slots, 1)
            ),
        )
        messages = [Message("system", prompts.BANK_SYSTEM), Message("user", prompt)]
        draft = self._call(messages, VerbBankDraft)
        accepted, problems = self._accept_sentences(infinitive, slots, draft.sentences)
        if problems:
            self.stats.repairs += 1
            self.progress(f"{infinitive}: repairing {len(problems)} sentence(s)")
            retry = [
                *messages,
                Message("assistant", draft.model_dump_json()),
                Message("user", prompts.VERB_REPAIR.format(problems="\n".join(problems.values()))),
            ]
            repaired = self._call(retry, SentenceRepair)
            fixed, _ = self._accept_sentences(
                infinitive, slots, [s for s in repaired.sentences if s.slot in problems]
            )
            accepted.update(fixed)
        issues: list[Issue] = []
        sentences = [accepted[i] for i in sorted(accepted)]
        bank = self._verb_bank(infinitive, draft, sentences, version)
        where = f"verbs/bank/{bank.id}.yaml"
        bad = {
            i.path.split(":")[-1]
            for i in check_verb_bank(bank, self.ref, where)
            if i.severity == "error"
        }
        if bad:
            kept = [s for i, s in enumerate(sentences) if f"sentences.{i}" not in bad]
            issues.append(
                Issue(
                    "warning",
                    where,
                    f"dropped {len(sentences) - len(kept)} sentence(s) that failed the checks",
                )
            )
            bank = self._verb_bank(infinitive, draft, kept, version)
        missing = len(slots) - len(bank.sentences)
        if missing:
            issues.append(
                Issue("warning", where, f"{missing} of {len(slots)} slots have no valid sentence")
            )
        issues += check_verb_bank(bank, self.ref, where)
        return bank, issues

    def _slot_line(self, infinitive: str, index: int, tense: str, person: str) -> str:
        form = forms_for(self.ref, infinitive, tense)[person][0]
        meta = TENSE_BY_KEY[tense]
        subject = "no subject" if tense.startswith("imperatif") else SUBJECT_LABELS[person]
        return f"{index}. {meta.label} ({subject}): « {form} »"

    def _accept_sentences(
        self, infinitive: str, slots: list[tuple[str, str]], drafts: list[SentenceDraft]
    ) -> tuple[dict[int, VerbSentence], dict[int, str]]:
        accepted: dict[int, VerbSentence] = {}
        problems: dict[int, str] = {}
        for draft in drafts:
            if not 1 <= draft.slot <= len(slots) or draft.slot in accepted:
                continue
            tense, person = slots[draft.slot - 1]
            fr, en = str(tidy(draft.fr.strip())), str(tidy(draft.en.strip()))
            found = find_form(self.ref, infinitive, tense, person, fr)
            if found is None:
                form = forms_for(self.ref, infinitive, tense)[person][0]
                problems[draft.slot] = (
                    f"- slot {draft.slot}: « {form} » ({TENSE_BY_KEY[tense].label}) is not in "
                    f"« {fr} »"
                )
                continue
            try:
                accepted[draft.slot] = VerbSentence.model_validate(
                    {
                        "tense": tense,
                        "person": person,
                        "fr": fr,
                        "form": found,
                        "en": en,
                        "region": "qc"
                        if self.ref.is_quebec_word(infinitive) or self.ref.quebec_terms_in(fr)
                        else "common",
                    }
                )
            except ValidationError as exc:
                problems[draft.slot] = f"- slot {draft.slot}: {exc.errors()[0]['msg']}"
        for i in range(1, len(slots) + 1):
            if i not in accepted and i not in problems:
                tense, person = slots[i - 1]
                form = forms_for(self.ref, infinitive, tense)[person][0]
                problems[i] = f"- slot {i}: missing (needs « {form} »)"
        return accepted, problems

    def _verb_bank(
        self, infinitive: str, draft: VerbBankDraft, sentences: list[VerbSentence], version: int
    ) -> VerbBank:
        data: dict[str, Any] = {
            "id": verb_slug(infinitive),
            "content_version": version,
            "infinitive": infinitive,
            "en": _gloss(draft.gloss) or infinitive,
            "note": _note(draft.note),
            "sentences": [s.model_dump() for s in sentences],
        }
        bank = VerbBank.model_validate(data)
        return bank.model_copy(update={"provenance": self._provenance(bank, "bank.verb")})

    # vocabulary sets -------------------------------------------------------------------------

    def vocab_set(self, theme: VocabTheme, *, version: int = 1) -> tuple[VocabSet, list[Issue]]:
        where = f"vocabulary/sets/{theme.id}.yaml"
        issues: list[Issue] = []
        lexicon = self._lexicon(theme.title, theme.scope, theme.quebec_focus or "")
        cleaned: list[WordDraft] = []
        target = theme.size + 4
        for _ in range(4):  # small batches: long lists overrun the token and time limits
            if len(cleaned) >= target:
                break
            listed = ", ".join(w.fr for w in cleaned)
            words_prompt = prompts.VOCAB_WORDS.format(
                title=theme.title,
                title_en=theme.title_en,
                level=theme.level,
                scope=theme.scope,
                quebec_focus=theme.quebec_focus or "none",
                lexicon=lexicon,
                count=min(WORD_BATCH, target - len(cleaned) + 2),
            ) + (f"\nAlready listed (do not repeat): {listed}" if listed else "")
            words = self._call(
                [Message("system", prompts.BANK_SYSTEM), Message("user", words_prompt)], WordList
            )
            known = {normalize(w.fr) for w in cleaned}
            fresh = self._clean_words(words.entries, theme, where, issues)
            cleaned += [w for w in fresh if normalize(w.fr) not in known]
        cleaned = cleaned[: theme.size]
        examples: dict[int, ExampleDraft] = {}
        for start in range(0, len(cleaned), EXAMPLE_BATCH):
            examples.update(
                self._examples(
                    theme, cleaned, range(start, min(start + EXAMPLE_BATCH, len(cleaned)))
                )
            )
        retry = [
            i
            for i, w in enumerate(cleaned)
            if i not in examples or not uses_word(w.fr, examples[i].example_fr)
        ]
        if retry:
            self.stats.repairs += 1
            self.progress(f"{theme.id}: rewriting {len(retry)} example(s)")
            examples.update(self._examples(theme, cleaned, retry))
        entries: list[VocabEntry] = []
        ids: set[str] = set()
        for i, word in enumerate(cleaned):
            example = examples.get(i)
            if example is None:
                issues.append(Issue("warning", where, f"dropped {word.fr!r}: no example"))
                continue
            entry_id = _unique_id(verb_slug(word.fr), ids)
            try:
                entries.append(_entry(entry_id, word, example))
                ids.add(entry_id)
            except ValidationError as exc:
                issues.append(
                    Issue("warning", where, f"dropped {word.fr!r}: {exc.errors()[0]['msg']}")
                )
        vocab = self._vocab_set(theme, entries, version)
        bad = {
            i.path.split(":")[-1]
            for i in check_vocab_set(vocab, self.ref, where)
            if i.severity == "error"
        }
        if bad:
            issues.append(
                Issue(
                    "warning",
                    where,
                    f"dropped entries that failed the checks: {', '.join(sorted(bad))}",
                )
            )
            vocab = self._vocab_set(theme, [e for e in entries if e.id not in bad], version)
        issues += check_vocab_set(vocab, self.ref, where)
        return vocab, issues

    def _clean_words(
        self, drafts: list[WordDraft], theme: VocabTheme, where: str, issues: list[Issue]
    ) -> list[WordDraft]:
        out: list[WordDraft] = []
        seen: set[str] = set()
        for draft in drafts:
            word = draft.model_copy(update={"fr": draft.fr.strip(), "en": draft.en.strip()})
            if match := _ARTICLE.match(word.fr):
                gender = _ARTICLE_GENDER.get((match.group(1) or "").lower())
                word = word.model_copy(
                    update={
                        "fr": word.fr[match.end() :],
                        "gender": word.gender if word.gender != "none" else gender or "none",
                    }
                )
            key = normalize(word.fr)
            if not key or key in seen:
                continue
            seen.add(key)
            if word.pos == "noun":
                lexique = self.ref.noun_gender(word.fr)
                if lexique in ("m", "f") and lexique != word.gender:
                    issues.append(
                        Issue(
                            "warning",
                            where,
                            f"{word.fr!r}: gender corrected to {lexique} (Lexique)",
                        )
                    )
                    word = word.model_copy(update={"gender": lexique})
                elif word.gender == "none":
                    word = word.model_copy(update={"pos": "expression"})
            elif word.gender != "none":
                word = word.model_copy(update={"gender": "none"})
            if word.region == "qc" and self.ref.quebec and not self.ref.quebec_terms_in(word.fr):
                issues.append(
                    Issue(
                        "warning",
                        where,
                        f"{word.fr!r}: Québec claim not in the verified lexicon; marked common",
                    )
                )
                word = word.model_copy(update={"region": "common"})
            out.append(word)
        return out

    def _examples(
        self, theme: VocabTheme, words: list[WordDraft], indices: Any
    ) -> dict[int, ExampleDraft]:
        indices = list(indices)
        lines = []
        for i in indices:
            w = words[i]
            article = f" ({w.gender})" if w.gender != "none" else ""
            region = ", Québec" if w.region == "qc" else ""
            lines.append(f"{i}. {w.fr}{article}: {w.en} [{w.pos}{region}]")
        lexicon = self._lexicon(*(words[i].fr for i in indices))
        prompt = prompts.VOCAB_EXAMPLES.format(
            title=theme.title,
            title_en=theme.title_en,
            level=theme.level,
            lexicon=lexicon,
            words="\n".join(lines),
        )
        result = self._call(
            [Message("system", prompts.BANK_SYSTEM), Message("user", prompt)], ExampleList
        )
        return {e.index: e for e in result.items if e.index in indices and e.example_fr.strip()}

    def _vocab_set(self, theme: VocabTheme, entries: list[VocabEntry], version: int) -> VocabSet:
        vocab = VocabSet(
            id=theme.id,
            content_version=version,
            level=theme.level,
            title=theme.title,
            title_en=theme.title_en,
            entries=entries,
        )
        return vocab.model_copy(update={"provenance": self._provenance(vocab, "bank.vocab")})

    # revision from reviewer notes ----------------------------------------------------------

    def revise_sentence(
        self, bank: VerbBank, index: int, problem: str, fix: str
    ) -> VerbSentence | None:
        s = bank.sentences[index]
        prompt = (
            prompts.BANK_REVISE.format(
                item=f"Slot 1: {TENSE_BY_KEY[s.tense].label} of {bank.infinitive} "
                f"(« {s.person} »): {s.fr} — {s.en}",
                problem=problem,
                fix=fix or "-",
            )
            + f"\nThe sentence must still contain the {TENSE_BY_KEY[s.tense].label} form "
            f"« {s.form} » (agreement may change). Use slot 1."
        )
        result = self._call(
            [Message("system", prompts.BANK_SYSTEM), Message("user", prompt)], SentenceRepair
        )
        accepted, _ = self._accept_sentences(
            bank.infinitive, [(s.tense, s.person)], result.sentences[:1]
        )
        return accepted.get(1)

    def revise_gloss(self, bank: VerbBank, problem: str, fix: str) -> str | None:
        prompt = prompts.BANK_REVISE.format(
            item=f"English gloss of « {bank.infinitive} »: {bank.en}",
            problem=problem,
            fix=fix or "-",
        )
        result = self._call(
            [Message("system", prompts.BANK_SYSTEM), Message("user", prompt)], GlossDraft
        )
        return str(tidy(result.en.strip())) or None

    def revise_entry(
        self, vocab: VocabSet, entry: VocabEntry, problem: str, fix: str
    ) -> VocabEntry | None:
        prompt = prompts.BANK_REVISE.format(
            item=entry.model_dump_json(exclude_none=True), problem=problem, fix=fix or "-"
        )
        result = self._call(
            [Message("system", prompts.BANK_SYSTEM), Message("user", prompt)], EntryDraft
        )
        theme = VocabTheme(
            id=vocab.id, level=vocab.level, title=vocab.title, title_en=vocab.title_en, scope="-"
        )
        issues: list[Issue] = []
        cleaned = self._clean_words([result], theme, "revise", issues)
        if not cleaned:
            return None
        example = ExampleDraft(
            index=0, example_fr=result.example_fr, example_en=result.example_en, note=result.note
        )
        try:
            revised = _entry(entry.id, cleaned[0], example)
        except ValidationError:
            return None
        others = {normalize(e.fr) for e in vocab.entries if e.id != entry.id}
        if normalize(revised.fr) in others:
            return None  # the rewrite turned it into another word of the set
        errors = [
            i for i in check_vocab_entry(revised, self.ref, "revise") if i.severity == "error"
        ]
        return None if errors else revised

    # plumbing ------------------------------------------------------------------------------

    def _lexicon(self, *texts: str) -> str:
        # Only the entries the texts mention: a generic sample ends up in every set and
        # sentence (souper in a nature set, « ouvrir le souper »).
        terms = self.ref.quebec_terms_in(*texts) if texts else []
        if not terms:
            return ""
        entries = "\n".join(
            f"- {t.term}: {t.meaning} (France: {t.france}; {t.formality})" for t in terms
        )
        return prompts.LEXICON.format(entries=entries) + "\n"

    def _call[T: BaseModel](self, messages: list[Message], schema: type[T]) -> T:
        started = time.perf_counter()
        obj, completion = complete_structured(
            self.chat, messages, schema, max_tokens=MAX_TOKENS, temperature=0.5
        )
        self.stats.calls += 1
        self.stats.seconds += time.perf_counter() - started
        self.stats.tokens += completion.completion_tokens or 0
        return obj

    def _provenance(self, model: BaseModel, prompt: str) -> Provenance:
        return Provenance(
            generator=self.model_name,
            prompts={"bank.system": "1", prompt: prompts.PROMPT_VERSIONS[prompt]},
            generated_at=datetime.now(UTC),
            generated_hash=content_hash(model),
        )


def _gloss(text: str) -> str:
    """The gloss alone: small models sometimes wrap it in headings ("Gloss: to go")."""
    text = str(tidy(text.strip()))
    if match := re.search(r"gloss\s*:\s*([^\n]+)", text, re.IGNORECASE):
        text = match.group(1)
    return text.splitlines()[0].strip(" .") if text else ""


def _note(text: str) -> str | None:
    text = str(tidy(text.strip()))
    if match := re.search(r"(?:usage )?note\s*:\s*(.+)", text, re.IGNORECASE | re.DOTALL):
        text = match.group(1).strip()
    if not re.search(r"\w{2}", text) or "frenchia" in text.casefold():
        return None
    if len(text) > 240 or "\n" in text:
        return None
    return text


def _no_imperative(infinitive: str) -> bool:
    return infinitive in NO_IMPERATIVE


def _unique_id(base: str, used: set[str]) -> str:
    candidate, n = base or "mot", 2
    while candidate in used:
        candidate, n = f"{base}-{n}", n + 1
    return candidate


def _entry(entry_id: str, word: WordDraft, example: ExampleDraft) -> VocabEntry:
    return VocabEntry(
        id=entry_id,
        fr=word.fr,
        en=str(tidy(word.en)),
        pos=word.pos,
        gender=None if word.gender == "none" else word.gender,
        plural=word.plural.strip() or None,
        region=word.region,
        formality=word.formality,
        example_fr=str(tidy(example.example_fr.strip())),
        example_en=str(tidy(example.example_en.strip())),
        note=clean_note(word.region, example.note),
    )


def clean_note(region: str, note: str) -> str | None:
    """Drop notes small models attach where they don't belong: a France equivalent on a word
    that isn't Québec usage, or a comment about the prompt itself."""
    text = str(tidy(note.strip()))
    if not text:
        return None
    if region != "qc" and text.casefold().startswith("france"):
        return None
    if re.search(r"\b(previous|above|this) (example|sentence|word)\b", text, re.IGNORECASE):
        return None
    return text
