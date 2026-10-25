"""Conjugation lookups on the reference data: tense metadata, the accepted forms for a
(verb, tense, person), and deterministic grading with a diagnosis of wrong answers.

No LLM is involved anywhere here: the reference (verbecc, cross-checked with mlconjug3) is the
only authority on what a correct form is."""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal

from .reference import Reference, normalize, participle_agreements

PERSONS = ("je", "tu", "il", "nous", "vous", "ils")
SUBJECT_LABELS = {
    "je": "je",
    "tu": "tu",
    "il": "il/elle/on",
    "nous": "nous",
    "vous": "vous",
    "ils": "ils/elles",
}
FUTUR_PROCHE = "indicatif.futur_proche"
VOWELS = "aeiouyhéèêëàâîïôûùœ"


@dataclass(frozen=True)
class Tense:
    key: str
    label: str
    label_en: str
    level: str
    mood: str
    compound: bool = False
    drill: bool = True
    """Passé simple is for recognition only: shown in tables, never drilled."""


TENSES = (
    Tense("indicatif.present", "Présent", "Present", "A1", "Indicatif"),
    Tense(FUTUR_PROCHE, "Futur proche", "Near future (aller + infinitive)", "A1", "Indicatif"),
    Tense("indicatif.passe_compose", "Passé composé", "Compound past", "A2", "Indicatif", True),
    Tense("indicatif.imparfait", "Imparfait", "Imperfect", "A2", "Indicatif"),
    Tense("indicatif.futur_simple", "Futur simple", "Simple future", "A2", "Indicatif"),
    Tense("imperatif.present", "Impératif", "Imperative", "A2", "Impératif"),
    Tense("conditionnel.present", "Conditionnel présent", "Conditional", "B1", "Conditionnel"),
    Tense("indicatif.plus_que_parfait", "Plus-que-parfait", "Pluperfect", "B1", "Indicatif", True),
    Tense("subjonctif.present", "Subjonctif présent", "Present subjunctive", "B1", "Subjonctif"),
    Tense(
        "conditionnel.passe", "Conditionnel passé", "Past conditional", "B2", "Conditionnel", True
    ),
    Tense(
        "indicatif.futur_anterieur", "Futur antérieur", "Future perfect", "B2", "Indicatif", True
    ),
    Tense("subjonctif.passe", "Subjonctif passé", "Past subjunctive", "B2", "Subjonctif", True),
    Tense(
        "indicatif.passe_simple",
        "Passé simple",
        "Simple past (literary)",
        "B2",
        "Indicatif",
        drill=False,
    ),
)
TENSE_BY_KEY = {t.key: t for t in TENSES}

# Tense of the auxiliary in each compound tense (for verbs that also take avoir: j'ai sorti).
_AUX_TENSE = {
    "indicatif.passe_compose": "indicatif.present",
    "indicatif.plus_que_parfait": "indicatif.imparfait",
    "indicatif.futur_anterieur": "indicatif.futur_simple",
    "conditionnel.passe": "conditionnel.present",
    "subjonctif.passe": "subjonctif.present",
}
_REFLEXIVE = {"je": "me", "tu": "te", "il": "se", "nous": "nous", "vous": "vous", "ils": "se"}
_SUBJECTS = {
    "je": ("je", "j'"),
    "tu": ("tu",),
    "il": ("il", "elle", "on"),
    "nous": ("nous",),
    "vous": ("vous",),
    "ils": ("ils", "elles"),
}

Result = Literal["correct", "accent", "incorrect"]
Diagnosis = Literal[
    "",
    "accents",
    "infinitive",
    "wrong_person",
    "wrong_tense",
    "wrong_auxiliary",
    "auxiliary_form",
    "participle",
    "agreement",
    "spelling",
    "incorrect",
]


def bare_infinitive(infinitive: str) -> str:
    """se lever -> lever, s'asseoir -> asseoir."""
    return re.sub(r"^(se |s')", "", infinitive)


def elide(word: str, following: str) -> str:
    """je + aime -> j'aime; me + appelle -> m'appelle (only the clitics that elide)."""
    if word in ("je", "me", "te", "se", "que") and following[:1].lower() in VOWELS:
        return word[:-1] + "'"
    return word + " "


def with_subject(person: str, form: str, tense: str, subject: str | None = None) -> str:
    """The form as it is said: j'ai mangé, que tu partes, il se lève; impératif unchanged.
    `subject` overrides the pronoun (elle, on, elles)."""
    if tense.startswith("imperatif"):
        return form
    text = elide(subject or person, form) + form
    if tense.startswith("subjonctif"):
        text = elide("que", text) + text
    return text


def forms_for(ref: Reference, infinitive: str, tense: str) -> dict[str, list[str]]:
    """person -> forms (primary first, then accepted spelling variants)."""
    verb = ref.verbs[infinitive]
    if tense == FUTUR_PROCHE:
        aller = ref.verbs["aller"]["forms"]["indicatif.present"]
        bare = bare_infinitive(infinitive)
        if bare == infinitive:
            return {p: [f"{aller[p]} {infinitive}"] for p in PERSONS}
        return {p: [f"{aller[p]} {elide(_REFLEXIVE[p], bare)}{bare}"] for p in PERSONS}
    out: dict[str, list[str]] = {}
    for person, form in verb["forms"].get(tense, {}).items():
        variants = verb.get("variants", {}).get(tense, {}).get(person, [])
        out[person] = list(dict.fromkeys([form, *variants]))
    return out


def conjugation_table(ref: Reference, infinitive: str) -> list[dict[str, Any]]:
    """Every tense of a verb for display: [{tense, label, ..., rows: [{person, form, said}]}]."""
    table = []
    for tense in TENSES:
        forms = forms_for(ref, infinitive, tense.key)
        if not forms:
            continue
        table.append(
            {
                "tense": tense.key,
                "label": tense.label,
                "label_en": tense.label_en,
                "mood": tense.mood,
                "level": tense.level,
                "rows": [
                    {
                        "person": person,
                        "form": forms[person][0],
                        "variants": forms[person][1:],
                        "said": with_subject(person, forms[person][0], tense.key),
                    }
                    for person in PERSONS
                    if person in forms
                ],
            }
        )
    return table


def _agrees(person: str, participle: str, feminine: bool | None) -> list[str]:
    """Agreed participles allowed for a subject, masculine first (vous: one person or more)."""
    m, f, mp, fp = participle, participle + "e", *_plural(participle)
    if person in ("je", "tu", "il"):
        options = {False: [m], True: [f], None: [m, f]}
    elif person == "vous":
        options = {False: [mp, m], True: [fp, f], None: [mp, m, fp, f]}
    else:
        options = {False: [mp], True: [fp], None: [mp, fp]}
    return options[feminine]


def _plural(participle: str) -> tuple[str, str]:
    mp = participle if participle.endswith(("s", "x")) else participle + "s"
    return mp, participle + "es"


def accepted_forms(
    ref: Reference, infinitive: str, tense: str, person: str, *, feminine: bool | None = None
) -> list[str]:
    """Every correct answer (normalised, without subject) for a (verb, tense, person).

    Compound tenses with être accept the agreed participle (suis allée); verbs that take both
    auxiliaries accept avoir too (j'ai sorti la poubelle). `feminine` narrows agreement when
    the learner wrote elle/elles."""
    forms = [normalize(f) for f in forms_for(ref, infinitive, tense).get(person, [])]
    meta = TENSE_BY_KEY.get(tense)
    if not forms or meta is None or not meta.compound:
        return forms
    verb = ref.verbs[infinitive]
    participle = normalize(verb["participle_past"])
    out: list[str] = []
    takes_etre = verb["auxiliary"] in ("être", "both") or verb.get("pronominal")
    for form in forms:
        head, last = form.rsplit(" ", 1)
        if takes_etre and last in participle_agreements(participle):
            out += [f"{head} {p}" for p in _agrees(person, participle, feminine)]
        else:
            out.append(form)
    if verb["auxiliary"] == "both":
        aux = ref.verbs["avoir"]["forms"][_AUX_TENSE[tense]][person]
        out.append(f"{normalize(aux)} {participle}")
    return list(dict.fromkeys(out))


@dataclass
class ConjugationGrade:
    result: Result
    expected: str
    """The model answer with its subject, e.g. « nous sommes allés »."""
    accepted: list[str]
    diagnosis: Diagnosis = ""
    message: str = ""
    details: dict[str, str] = field(default_factory=dict)


def strip_accents(text: str) -> str:
    text = text.replace("œ", "oe").replace("æ", "ae")
    return "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))


def _clean(answer: str) -> str:
    return normalize(re.sub(r"[.!?,;:«»\"]", " ", answer))


def _strip_subject(answer: str, person: str, tense: str) -> tuple[str, str | None]:
    """(answer without que/subject pronoun, the pronoun written or None)."""
    text = re.sub(r"^(que |qu')", "", answer) if tense.startswith("subjonctif") else answer
    if tense.startswith("imperatif"):
        return text, None
    for subject in _SUBJECTS[person]:
        sep = "" if subject.endswith("'") else " "
        if text.startswith(subject + sep) and len(text) > len(subject) + len(sep):
            return text[len(subject) + len(sep) :], subject
    return text, None


def grade_conjugation(
    ref: Reference,
    infinitive: str,
    tense: str,
    person: str,
    answer: str,
    *,
    expected_form: str | None = None,
) -> ConjugationGrade:
    """Grade a typed form. `expected_form` is the exact form required by a context sentence
    (it fixes agreement: « Marie ___ (partir) » needs « est partie »)."""
    raw = _clean(answer)
    stripped, subject = _strip_subject(raw, person, tense)
    feminine = {"elle": True, "elles": True, "il": False, "ils": False}.get(subject or "")
    general = accepted_forms(ref, infinitive, tense, person)
    if expected_form is not None:
        target = normalize(expected_form)
        accepted = [target] + [
            f for f in general if f != target and f.split()[-1] == target.split()[-1]
        ]
    else:
        accepted = accepted_forms(ref, infinitive, tense, person, feminine=feminine)
    if expected_form is not None:
        expected = expected_form  # the sentence supplies the subject
    elif feminine:
        expected = with_subject(person, accepted[0], tense, subject)
    else:
        expected = with_subject(person, general[0], tense)
    grade = ConjugationGrade("incorrect", expected, accepted)

    candidates = [c for c in dict.fromkeys([stripped, raw]) if c]
    if any(c in accepted for c in candidates):
        grade.result = "correct"
        return grade
    if any(strip_accents(c) == strip_accents(a) for c in candidates for a in accepted):
        grade.result, grade.diagnosis = "accent", "accents"
        grade.message = f"Almost: check the accents ({expected})."
        return grade
    grade.diagnosis, grade.message = _diagnose(
        ref, infinitive, tense, person, stripped, general, accepted
    )
    return grade


def _diagnose(
    ref: Reference,
    infinitive: str,
    tense: str,
    person: str,
    answer: str,
    general: list[str],
    accepted: list[str],
) -> tuple[Diagnosis, str]:
    verb = ref.verbs[infinitive]
    bare = strip_accents(answer)
    if bare in (strip_accents(normalize(infinitive)), strip_accents(bare_infinitive(infinitive))):
        return "infinitive", "That's the infinitive: conjugate it for the subject."
    if answer in general:
        return "agreement", "Check the agreement of the past participle with the subject."
    for other in PERSONS:
        if other != person and _matches(answer, accepted_forms(ref, infinitive, tense, other)):
            return "wrong_person", f"That's the « {SUBJECT_LABELS[other]} » form."
    for other_tense in TENSES:
        if other_tense.key == tense:
            continue
        if _matches(answer, accepted_forms(ref, infinitive, other_tense.key, person)):
            return "wrong_tense", f"That's the {other_tense.label.lower()}."
    meta = TENSE_BY_KEY[tense]
    if meta.compound and " " in answer:
        aux_written, participle_written = answer.rsplit(" ", 1)
        participle = normalize(verb["participle_past"])
        aux = "être" if verb["auxiliary"] == "être" or verb.get("pronominal") else "avoir"
        other_aux = "avoir" if aux == "être" else "être"
        aux_tense = _AUX_TENSE[tense]
        other_form = normalize(ref.verbs[other_aux]["forms"][aux_tense][person])
        if strip_accents(participle_written) in {
            strip_accents(p) for p in participle_agreements(participle)
        }:
            if aux_written.endswith(other_form):
                return (
                    "wrong_auxiliary",
                    f"{infinitive} takes {aux} in compound tenses: {accepted[0]}.",
                )
            return "auxiliary_form", f"Check the form of the auxiliary {aux}: {accepted[0]}."
        if any(aux_written == a.rsplit(" ", 1)[0] for a in accepted):
            return (
                "participle",
                f"The past participle of {infinitive} is « {verb['participle_past']} ».",
            )
    if min(_distance(answer, a) for a in accepted) <= 2:
        return "spelling", "Close: check the spelling."
    return "incorrect", ""


def _matches(answer: str, forms: list[str]) -> bool:
    return answer in forms or strip_accents(answer) in {strip_accents(f) for f in forms}


def _distance(a: str, b: str) -> int:
    """Levenshtein distance (small strings only)."""
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def find_form(
    ref: Reference, infinitive: str, tense: str, person: str, sentence: str
) -> str | None:
    """The accepted form of (verb, tense, person) as written in a sentence (longest match), or
    None. Used to validate generated context sentences."""
    text = unicodedata.normalize("NFC", sentence)
    # « nous levons » of se lever starts with the reflexive pronoun; the subject must come
    # before it (« nous nous levons »), or « Nous levons les rideaux » would pass.
    doubled = bool(ref.verbs[infinitive].get("pronominal")) and person in ("nous", "vous")
    best: str | None = None
    for form in accepted_forms(ref, infinitive, tense, person):
        escaped = re.escape(form).replace("'", "['’]").replace(r"\ ", r"\s+")
        subject = ""
        if doubled and form.casefold().startswith(person + " "):
            subject = person + r"\s+"
        pattern = r"(?<![\w-])" + subject + "(" + escaped + r")(?![\w-])"
        match = re.search(pattern, text, re.IGNORECASE)
        if match and (best is None or len(match.group(1)) > len(best)):
            best = match.group(1)
    return best


def verb_slug(infinitive: str) -> str:
    """File/URL id for a verb: être -> etre, se lever -> se-lever, s'asseoir -> s-asseoir."""
    return re.sub(r"[^a-z0-9]+", "-", strip_accents(infinitive.casefold())).strip("-")
