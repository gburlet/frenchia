import json
import re
from collections.abc import AsyncIterator, Callable, Sequence
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings as django_settings

from authoring.bank_workflow import (
    export_reviews,
    import_reviews,
    promote,
    read,
    write,
)
from authoring.bankgen import BankGenerator
from contentkit.models import VocabTheme
from contentkit.reference import Reference
from inference.llm import Completion, Message

REF = Reference.load(Path(django_settings.CONTENT_DIR))
pytestmark = pytest.mark.skipif(not REF.verbs, reason="reference data not available")

Responder = Callable[[str, list[Message]], Any]


class Chat:
    """Answers each structured call through a responder keyed by schema title."""

    model = "scripted"

    def __init__(self, responder: Responder) -> None:
        self.responder = responder
        self.calls: list[str] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> Completion:
        title = (json_schema or {}).get("title", "")
        self.calls.append(title)
        data = self.responder(title, list(messages))
        return Completion(
            content=json.dumps(data, ensure_ascii=False), model="scripted", latency_ms=1
        )

    async def stream(self, messages: Sequence[Message], **kwargs: Any) -> AsyncIterator[str]:
        yield ""

    def warm(self) -> None: ...

    def health(self) -> bool:
        return True


def slot_forms(prompt: str) -> dict[int, str]:
    return {int(n): form for n, form in re.findall(r"^(\d+)\. .*« (.+) »$", prompt, re.M)}


SENTENCES = {
    "vais": "Je vais au dépanneur ce soir.",
    "vas": "Tu vas au chalet en fin de semaine ?",
    "va": "Elle va au travail en autobus.",
    "allons": "Nous allons souper chez Marie.",
    "allez": "Vous allez au cinéma demain ?",
    "vont": "Ils vont au parc après l'école.",
}


def aller_responder(title: str, messages: list[Message]) -> Any:
    prompt = messages[-1].content
    if title == "VerbBankDraft":
        forms = slot_forms(prompt)
        sentences = []
        for slot, form in forms.items():
            if slot == 2:  # forgets the form: must be repaired
                fr = "Je mange une pomme."
            else:
                fr = SENTENCES.get(form, f"Hier, c'est vrai, {form} tout le temps.")
            sentences.append({"slot": slot, "fr": fr, "en": "A sentence."})
        return {"sentences": sentences, "en": "Gloss: to go", "note": "Frenchia note"}
    if title == "SentenceRepair":
        slot = int(re.search(r"slot (\d+)", prompt).group(1))  # type: ignore[union-attr]
        return {"sentences": [{"slot": slot, "fr": "Elles vont au dépanneur.", "en": "x"}]}
    raise AssertionError(title)


def test_verb_bank_keeps_only_sentences_with_reference_forms() -> None:
    chat = Chat(aller_responder)
    generator = BankGenerator(chat, REF, model_name="scripted")
    slots = generator.slots("aller")
    assert len(slots) == 10 and slots[0][0] == "indicatif.present"
    bank, _issues = generator.verb_bank("aller")
    assert bank.en == "to go" and bank.note is None
    assert chat.calls == ["VerbBankDraft", "SentenceRepair"]
    for s in bank.sentences:
        assert s.form.casefold() in s.fr.casefold()
    by_slot = {(s.tense, s.person): s for s in bank.sentences}
    present = [s for s in bank.sentences if s.tense == "indicatif.present"]
    assert len(present) == 2  # slot 2 was repaired with "vont" only if it was the ils slot
    assert any(s.region == "qc" for s in bank.sentences)  # derived from the lexicon
    assert all(
        s.region == ("qc" if REF.quebec_terms_in(s.fr) else "common") for s in by_slot.values()
    )
    assert bank.provenance is not None and bank.provenance.generator == "scripted"


WORDS = [
    {"fr": "la tuque", "en": "winter hat", "pos": "noun", "gender": "none", "region": "qc"},
    {"fr": "neige", "en": "snow", "pos": "noun", "gender": "m", "region": "common"},
    {"fr": "neige", "en": "snow", "pos": "noun", "gender": "f", "region": "common"},
    {"fr": "froid", "en": "cold", "pos": "adjective", "gender": "m", "region": "common"},
    {"fr": "chalet", "en": "cottage", "pos": "noun", "gender": "m", "region": "qc"},
    {"fr": "vent", "en": "wind", "pos": "noun", "gender": "m", "region": "common"},
    {"fr": "glace", "en": "ice", "pos": "noun", "gender": "f", "region": "common"},
    {"fr": "tempête", "en": "storm", "pos": "noun", "gender": "f", "region": "common"},
]


def vocab_responder(title: str, messages: list[Message]) -> Any:
    prompt = messages[-1].content
    if title == "WordList":
        return {"entries": [{**w, "formality": "standard", "plural": ""} for w in WORDS]}
    if title == "ExampleList":
        items = []
        for index, word in re.findall(r"^(\d+)\. ([^:(]+?)(?: \([mf]\))?:", prompt, re.M):
            items.append(
                {
                    "index": int(index),
                    "example_fr": f"J'aime beaucoup la {word.strip()} en hiver.",
                    "example_en": "I like it.",
                    "note": "",
                }
            )
        return {"items": items}
    if title == "EntryDraft":
        return {
            "fr": "tuque",
            "en": "toque, knit hat",
            "pos": "noun",
            "gender": "f",
            "region": "qc",
            "formality": "standard",
            "plural": "",
            "example_fr": "Mets ta tuque, il fait frette.",
            "example_en": "Put on your toque, it's freezing.",
            "note": "France: un bonnet",
        }
    raise AssertionError(title)


THEME = VocabTheme(
    id="a1-hiver",
    level="A1",
    title="L'hiver",
    title_en="Winter",
    scope="Winter.",
    size=8,
)


def test_vocab_set_cleans_articles_genders_duplicates_and_quebec_claims() -> None:
    generator = BankGenerator(Chat(vocab_responder), REF)
    vocab, issues = generator.vocab_set(THEME)
    entries = {e.fr: e for e in vocab.entries}
    assert list(entries) == ["tuque", "neige", "froid", "chalet", "vent", "glace", "tempête"]
    assert entries["tuque"].gender == "f" and entries["tuque"].region == "qc"
    assert entries["neige"].gender == "f"  # corrected from Lexique
    assert entries["froid"].gender is None
    assert entries["chalet"].region == "common"  # not in the verified lexicon
    messages = " ".join(str(i) for i in issues)
    assert "gender corrected" in messages and "marked common" in messages


def test_review_round_trip_revise_drop_and_promote(tmp_path: Path) -> None:
    root = tmp_path / "content"
    (root / "reference").mkdir(parents=True)
    generator = BankGenerator(Chat(vocab_responder), REF, model_name="scripted")
    vocab, _ = generator.vocab_set(THEME)
    write(root, "vocabulary", vocab)
    verbs = BankGenerator(Chat(aller_responder), REF)
    bank, _ = verbs.verb_bank("aller")
    write(root, "verbs", bank)

    assert sorted(export_reviews(root, REF, ("verbs", "vocabulary"))) == [
        "verbs-aller",
        "vocabulary-a1-hiver",
    ]
    review = root / "drafts" / "review"
    prompt = (review / "vocabulary-a1-hiver.prompt.txt").read_text()
    assert "tuque" in prompt and "JSON Schema" in prompt

    def finding(item: str, severity: str = "error") -> dict[str, str]:
        return {
            "item_id": item,
            "severity": severity,
            "category": "meaning",
            "problem": "wrong",
            "suggested_fix": "fix",
        }

    (review / "vocabulary-a1-hiver.findings.json").write_text(
        json.dumps({"issues": [finding("tuque"), finding("vent"), finding("glace", "suggestion")]})
    )
    (review / "verbs-aller.findings.json").write_text(
        json.dumps({"issues": [finding("s1"), finding("note")]})
    )

    def reviser(title: str, messages: list[Message]) -> Any:
        if title == "SentenceRepair":  # a rewrite without the form: the sentence is dropped
            return {"sentences": [{"slot": 1, "fr": "Je mange une pomme.", "en": "x"}]}
        return vocab_responder(title, messages)

    outcomes = {
        o.stem: o for o in import_reviews(root, REF, "haiku", BankGenerator(Chat(reviser), REF))
    }
    hiver = outcomes["vocabulary-a1-hiver"]
    assert (hiver.revised, hiver.dropped, hiver.reviewed) == (["tuque"], ["vent"], False)
    aller = outcomes["verbs-aller"]
    assert aller.dropped == ["s1", "note"] and aller.reviewed  # nothing revised: done
    assert not list(review.glob("*.findings.json"))

    updated = read(root / "drafts" / "vocabulary" / "a1-hiver.yaml", "vocabulary")
    assert "vent" not in {e.id for e in updated.entries}  # type: ignore[union-attr]
    # revised items need another review round before they can be published
    promoted, skipped = promote(root, REF, "vocabulary")
    assert promoted == [] and "not reviewed" in skipped[0]
    promoted, _ = promote(root, REF, "verbs")
    assert promoted == ["aller v1"]
    assert (root / "verbs" / "bank" / "aller.yaml").exists()
    assert not (root / "drafts" / "verbs" / "aller.yaml").exists()
