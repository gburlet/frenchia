"""Deterministic reference data (content/reference/) used to check generated content.

All files are optional: missing data disables the corresponding checks (with a warning)."""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .yamlio import load_yaml


def normalize(text: str) -> str:
    """Lowercase, NFC, straight apostrophes, single spaces: for comparisons only."""
    text = unicodedata.normalize("NFC", text).replace("’", "'").casefold()
    return " ".join(text.split())


class QuebecTerm(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    term: str
    match: list[str]
    """Regexes (case-insensitive) that find the term, including inflected forms."""
    meaning: str
    france: str
    formality: str
    notes: str | None = None


@dataclass
class Reference:
    root: Path
    nouns: dict[str, dict[str, Any]] = field(default_factory=dict)
    verbs: dict[str, dict[str, Any]] = field(default_factory=dict)
    quebec: list[QuebecTerm] = field(default_factory=list)

    @classmethod
    def load(cls, content_root: Path) -> "Reference":
        root = content_root / "reference"
        ref = cls(root)
        if (p := root / "nouns.json").exists():
            ref.nouns = json.loads(p.read_text(encoding="utf-8"))["nouns"]
        if (p := root / "conjugations.json").exists():
            ref.verbs = json.loads(p.read_text(encoding="utf-8"))["verbs"]
        if (p := root / "quebec.yaml").exists():
            ref.quebec = [QuebecTerm.model_validate(e) for e in load_yaml(p) or []]
        return ref

    def noun_gender(self, lemma: str) -> str | None:
        entry = self.nouns.get(normalize(lemma))
        return entry["gender"] if entry else None

    @cached_property
    def _forms(self) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for infinitive, verb in self.verbs.items():
            participle = normalize(verb["participle_past"])
            agreed = participle_agreements(participle)
            forms = {normalize(infinitive), normalize(verb["participle_present"]), *agreed}
            tenses = [*verb["forms"].values(), *verb.get("variants", {}).values()]
            if verb.get("auxiliary") == "both":
                tenses += self._avoir_compounds(participle)
            for tense in tenses:
                values = [
                    v
                    for value in tense.values()
                    for v in ([value] if isinstance(value, str) else value)
                ]
                for form in map(normalize, values):
                    forms.add(form)
                    *head, last = form.split()
                    # Compound tenses: the reference gives masculine forms; add agreed ones.
                    if head and last in (participle, participle + "s"):
                        forms.update(" ".join([*head, variant]) for variant in agreed)
            out[normalize(infinitive)] = forms
        return out

    def _avoir_compounds(self, participle: str) -> list[dict[str, str]]:
        """Compound forms with avoir for verbs that take both auxiliaries (j'ai sorti le chien)."""
        avoir = self.verbs.get("avoir")
        if avoir is None:
            return []
        aux_tenses = (
            "indicatif.present",
            "indicatif.imparfait",
            "indicatif.futur_simple",
            "conditionnel.present",
            "subjonctif.present",
        )
        return [
            {p: f"{form} {participle}" for p, form in avoir["forms"][t].items()} for t in aux_tenses
        ]

    def verb_forms(self, infinitive: str) -> set[str] | None:
        """Every reference form of a verb (all tenses/persons), or None if unknown."""
        return self._forms.get(normalize(infinitive))

    # Auxiliary forms say nothing about which verb is meant; skip them when finding verbs.
    _AUX_FORMS = frozenset(
        "ai as a avons avez ont suis es est sommes êtes sont avais avait étais était eu été "
        "aie aies ait soit sois soient aura serai sera".split()
    )

    @cached_property
    def _verb_index(self) -> dict[str, str]:
        """Single-word form -> infinitive (first verb wins for ambiguous forms)."""
        index: dict[str, str] = {}
        for infinitive, forms in self._forms.items():
            for form in forms:
                word = form.split()[-1]
                if " " not in form or word not in self._AUX_FORMS:
                    index.setdefault(word, infinitive)
        return index

    def verbs_in(self, *texts: str, limit: int = 4) -> list[str]:
        """Infinitives of the reference verbs that appear in the texts (in order of appearance)."""
        found: list[str] = []
        for text in texts:
            for word in re.findall(r"[\w'’-]+", normalize(text)):
                word = word.split("'")[-1]
                infinitive = self._verb_index.get(word)
                skip = word in self._AUX_FORMS or infinitive in ("avoir", "être")
                if infinitive and not skip and infinitive not in found:
                    found.append(infinitive)
        return found[:limit]

    def verb_facts(self, infinitive: str) -> str | None:
        """One line of authoritative facts for the tutor, e.g. aller: auxiliary être, ..."""
        verb = self.verbs.get(infinitive)
        if verb is None:
            return None
        forms = verb["forms"]
        present = forms.get("indicatif.present", {})
        compound = forms.get("indicatif.passe_compose", {})
        return (
            f"{infinitive}: auxiliary {verb['auxiliary']}; "
            f"past participle {verb['participle_past']}; "
            f"présent {_je(present.get('je', '?'))}, nous {present.get('nous', '?')}; "
            f"passé composé {_je(compound.get('je', '?'))}, nous {compound.get('nous', '?')}"
        )

    def quebec_terms_in(self, *texts: str) -> list[QuebecTerm]:
        """Lexicon entries found in the texts; a text that is exactly an entry's headword
        counts too (a vocabulary word « liqueur » has no determiner for the pattern)."""
        bare = {normalize(text) for text in texts}
        return [
            t
            for t in self.quebec
            if normalize(t.term) in bare
            or any(re.search(p, text, re.IGNORECASE) for p in t.match for text in texts)
        ]


def participle_agreements(participle: str) -> set[str]:
    """allé -> allé, allée, allés, allées; pris -> pris, prise, prises."""
    plural = participle if participle.endswith(("s", "x")) else participle + "s"
    return {participle, participle + "e", plural, participle + "es"}


def _je(form: str) -> str:
    """Subject pronoun with elision: j'ai, j'habite, je pars."""
    return f"j'{form}" if form[:1].lower() in "aeiouyhéèêàâîôûœ" else f"je {form}"
