# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verbecc==2.0.3",
#   "pyyaml==6.0.3",
# ]
# ///
"""Build deterministic French reference data for Frenchia.

Outputs (under content/reference/):
  nouns.json, conjugations.json, conjugation_disagreements.yaml

Run:  uv run tools/reference/build_reference.py

mlconjug3 (cross-check) cannot share an environment with verbecc (numpy pin
conflict, and its model only loads on Python 3.10), so it runs through the
helper tools/reference/mlconjug_dump.py in a separate uv environment.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import re
import subprocess
import sys
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
CACHE = HERE / ".cache"
OUT = ROOT / "content" / "reference"

LEXIQUE_URL = "https://www.lexique.org/databases/Lexique383/Lexique383.zip"
LEXIQUE_ZIP = CACHE / "Lexique383.zip"
LEXIQUE_TSV = "Lexique383.tsv"
FREQ_COL = "freqlemfilms2"  # lemma-level film-subtitle frequency (per million)

N_NOUNS = 15000
N_VERBS = 300

PERSONS = ["je", "tu", "il", "nous", "vous", "ils"]
IMP_PERSONS = ["tu", "nous", "vous"]

TENSES = {  # output key -> (verbecc mood, verbecc tense)
    "indicatif.present": ("indicatif", "présent"),
    "indicatif.imparfait": ("indicatif", "imparfait"),
    "indicatif.passe_compose": ("indicatif", "passé-composé"),
    "indicatif.plus_que_parfait": ("indicatif", "plus-que-parfait"),
    "indicatif.futur_simple": ("indicatif", "futur-simple"),
    "indicatif.futur_anterieur": ("indicatif", "futur-antérieur"),
    "indicatif.passe_simple": ("indicatif", "passé-simple"),
    "conditionnel.present": ("conditionnel", "présent"),
    "conditionnel.passe": ("conditionnel", "passé"),
    "subjonctif.present": ("subjonctif", "présent"),
    "subjonctif.passe": ("subjonctif", "passé"),
    "imperatif.present": ("imperatif", "imperatif-présent"),
}
SIMPLE_TENSES = [
    "indicatif.present", "indicatif.imparfait", "indicatif.futur_simple",
    "indicatif.passe_simple", "conditionnel.present", "subjonctif.present",
]

CURATED = [
    "s'appeler", "se lever", "se coucher", "se réveiller", "s'habiller", "se laver",
    "se promener", "se reposer", "se souvenir", "s'asseoir", "se dépêcher", "s'amuser",
    "se rencontrer", "se trouver", "se sentir", "s'occuper", "se marier", "s'ennuyer",
    "magasiner", "souper", "dîner", "déjeuner", "jaser", "niaiser", "placoter", "pogner",
]
# Verbs that take either auxiliary (verbecc only gives its default one).
BOTH_AUX = {"passer", "monter", "sortir", "descendre", "rentrer", "retourner"}
AUX_ODDITIES = {"avoir", "être"}  # kept (needed), listed for documentation only

ASSERTIONS = [
    ("aller", "indicatif.present", "ils", "vont"),
    ("être", "indicatif.imparfait", "nous", "étions"),
    ("faire", "conditionnel.present", "vous", "feriez"),
    ("pouvoir", "subjonctif.present", "je", "puisse"),
    ("avoir", "subjonctif.present", "il", "ait"),
    ("venir", "indicatif.passe_compose", "nous", "sommes venus"),
    ("se lever", "indicatif.present", "tu", "te lèves"),
    ("s'appeler", "indicatif.present", "je", "m'appelle"),
    ("prendre", "indicatif.present", "ils", "prennent"),
    ("finir", "indicatif.imparfait", "nous", "finissions"),
    ("vouloir", "conditionnel.present", "je", "voudrais"),
    ("se lever", "imperatif.present", "tu", "lève-toi"),
]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).replace("’", "'").replace("‘", "'")
    return re.sub(r"\s+", " ", s).strip()


def dump_json(path: Path, obj, sort_keys=True) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=sort_keys) + "\n",
        encoding="utf-8",
    )


# --------------------------------------------------------------------------
# Lexique
# --------------------------------------------------------------------------
def load_lexique() -> list[dict]:
    CACHE.mkdir(parents=True, exist_ok=True)
    if not LEXIQUE_ZIP.exists():
        print(f"downloading {LEXIQUE_URL}", file=sys.stderr)
        with urllib.request.urlopen(LEXIQUE_URL, timeout=120) as r:
            LEXIQUE_ZIP.write_bytes(r.read())
    with zipfile.ZipFile(LEXIQUE_ZIP) as z:
        raw = z.read(LEXIQUE_TSV).decode("utf-8")
    rd = csv.DictReader(io.StringIO(raw), delimiter="\t", quoting=csv.QUOTE_NONE)
    rows = list(rd)
    need = {"ortho", "lemme", "cgram", "genre", FREQ_COL}
    assert need <= set(rd.fieldnames or []), f"Lexique columns missing: {need - set(rd.fieldnames or [])}"
    assert len(rows) > 100_000, f"Lexique parsed suspiciously few rows: {len(rows)}"
    return rows


WORD_RE = re.compile(r"^[a-zàâäçéèêëîïôöùûüÿœæ]+(-[a-zàâäçéèêëîïôöùûüÿœæ]+)*$")


def lemma_freqs(rows, cgram: str) -> dict[str, float]:
    f: dict[str, float] = {}
    for r in rows:
        if r["cgram"] != cgram or not WORD_RE.match(r["lemme"]):
            continue
        v = float(r[FREQ_COL] or 0)
        if v > f.get(r["lemme"], -1):
            f[r["lemme"]] = v
    return f


def build_nouns(rows) -> dict:
    freq = lemma_freqs(rows, "NOM")
    genders: dict[str, set[str]] = {}
    for r in rows:
        if r["cgram"] == "NOM" and r["lemme"] in freq:
            g = genders.setdefault(r["lemme"], set())
            if r["genre"] in ("m", "f"):
                g.add(r["genre"])
    ranked = sorted(freq, key=lambda w: (-freq[w], w))[:N_NOUNS]
    nouns = {}
    for w in ranked:
        g = genders[w]
        # Lexique leaves `genre` blank when a form is gender-ambiguous
        # (élève, livre, tour); lemmas with no explicit gender -> "mf".
        gender = "mf" if len(g) != 1 else next(iter(g))
        nouns[w] = {"freq": round(freq[w], 2), "gender": gender}
    return {
        "schema_version": 1,
        "source": lexique_source(),
        "frequency_column": f"{FREQ_COL} (lemma frequency in film subtitles, occurrences per million); nouns are ordered by it descending, ties alphabetical",
        "gender_rule": "m/f if all gendered Lexique rows of the lemma agree; mf if both genders occur or Lexique leaves gender blank (epicene or meaning-dependent, e.g. élève, livre, tour)",
        "nouns": nouns,
    }


def lexique_source() -> dict:
    return {
        "name": "Lexique",
        "version": "3.83",
        "url": "http://www.lexique.org/",
        "download": LEXIQUE_URL,
        "license": "CC BY-SA 4.0",
        "citation": "New, B., Pallier, C., Brysbaert, M., Ferrand, L. (2004). Lexique 2: A new French lexical database. Behavior Research Methods, Instruments, & Computers, 36(3), 516-524.",
        "derived_dataset_license": "CC BY-SA 4.0",
    }


# --------------------------------------------------------------------------
# Conjugation
# --------------------------------------------------------------------------
SUBJ = {
    "je": ("je ", "j'"), "tu": ("tu ",), "il": ("il ",),
    "nous": ("nous ",), "vous": ("vous ",), "ils": ("ils ",),
}


def strip_subject(text: str, person: str) -> str:
    text = norm(text)
    if text.startswith("que "):
        text = text[4:]
    elif text.startswith("qu'"):
        text = text[3:]
    for p in SUBJ[person]:
        if text.startswith(p):
            return text[len(p):]
    raise ValueError(f"cannot strip subject {person!r} from {text!r}")


def pick_entries(entries, person):
    """Entries for a person; for gendered compound tenses keep masculine."""
    es = [e for e in entries if e.get("pr") == person]
    masc = [e for e in es if e.get("g") in (None, "m")]
    return masc or es


def split_forms(entries, person) -> list[str]:
    out = []
    for e in pick_entries(entries, person):
        for c in e["c"]:
            f = strip_subject(c, person)
            if f not in out:
                out.append(f)
    return out


def conjugate_verb(conj, name: str) -> dict | None:
    """Return the record for `name`, or None if defective/unconjugable."""
    pronominal = name.startswith("se ") or name.startswith("s'")
    base = name[3:] if name.startswith("se ") else name[2:] if name.startswith("s'") else name
    try:
        data = conj.conjugate(name).get_data()
    except Exception as e:  # noqa: BLE001
        print(f"skip {name}: {e!r}", file=sys.stderr)
        return None
    info = data["verb"]
    inferred = bool(info.get("predicted"))
    if inferred and info["template"] != "aim:er":
        raise AssertionError(f"{name}: predicted template {info['template']} is not the regular -er template")
    moods = data["moods"]
    forms, variants = {}, {}
    for key, (mood, tense) in TENSES.items():
        entries = moods.get(mood, {}).get(tense, [])
        if key == "imperatif.present":
            if len(entries) != 3:
                forms[key] = {}
                continue
            d = {}
            for p, e in zip(IMP_PERSONS, entries):
                alts = [norm(c) for c in e["c"]]
                d[p] = alts[0]
                if len(alts) > 1:
                    variants.setdefault(key, {})[p] = alts[1:]
            forms[key] = d
            continue
        d = {}
        for p in PERSONS:
            fs = split_forms(entries, p)
            if not fs:
                break
            d[p] = fs[0]
            if len(fs) > 1:
                variants.setdefault(key, {})[p] = fs[1:]
        else:
            forms[key] = d
            continue
        return None  # defective: some person missing in a required tense
    # participles
    part = moods["participe"]
    pp = [norm(c) for e in part["participe-passé"] if e.get("g") == "m" for c in e["c"]]
    pp_sing = re.sub(r"^étant ", "", pp[0])
    pres = norm(part["participe-présent"][0]["c"][0])

    # auxiliary from the il form of passé composé
    il = forms["indicatif.passe_compose"]["il"]
    toks = il.replace("'", "' ").split()
    aux = "être" if "est" in toks else "avoir"
    if pronominal:
        aux = "être"
    elif base in BOTH_AUX:
        aux = "both"

    nous_pres = forms["indicatif.present"]["nous"]
    if base == "aller":
        group = 3
    elif base.endswith("er"):
        group = 1
    elif base.endswith("ir") and nous_pres.endswith("issons"):
        group = 2
    else:
        group = 3

    rec = {
        "auxiliary": aux,
        "forms": forms,
        "group": group,
        "inferred": inferred,
        "participle_past": pp_sing,
        "participle_present": pres,
        "pronominal": pronominal,
    }
    if variants:
        rec["variants"] = variants
    return rec


def conjugation_source() -> dict:
    return {
        "primary": {"name": "verbecc", "version": "2.0.3", "license": "LGPL-3.0", "url": "https://github.com/bretttolbert/verbecc"},
        "cross_check": {"name": "mlconjug3", "version": "4.0.1", "license": "MIT", "url": "https://github.com/SekouDiaoNlp/mlconjug3"},
        "verb_selection": f"top {N_VERBS} Lexique 3.83 VER lemmas by {FREQ_COL} that verbecc knows and can fully conjugate, plus a curated set (pronominal and Quebec verbs)",
        "notes": "variants (optional per verb) lists alternate accepted forms beyond the primary one stored in forms. auxiliary 'both' verbs store verbecc's default-auxiliary compound forms.",
    }


def select_verbs(rows, conj) -> tuple[list[str], list[str]]:
    freq = lemma_freqs(rows, "VER")
    cand = sorted(freq, key=lambda w: (-freq[w], w))
    chosen, skipped = [], []
    for w in cand:
        if len(chosen) >= N_VERBS:
            break
        if not re.search(r"(er|ir|re|oir)$", w):
            continue
        try:
            d = conj.conjugate(w).get_data()
        except Exception:  # noqa: BLE001
            skipped.append(w)
            continue
        if d["verb"].get("predicted"):
            skipped.append(w)  # unknown to verbecc
            continue
        chosen.append(w)
    return chosen, skipped


def run_mlconjug(infinitives: list[str]) -> dict:
    CACHE.mkdir(parents=True, exist_ok=True)
    inp, outp = CACHE / "ml_in.json", CACHE / "ml_out.json"
    inp.write_text(json.dumps(infinitives, ensure_ascii=False), encoding="utf-8")
    subprocess.run(["uv", "run", "--quiet", str(HERE / "mlconjug_dump.py"), str(inp), str(outp)], check=True)
    return json.loads(outp.read_text(encoding="utf-8"))


REFL = {"je": ("me ", "m'"), "tu": ("te ", "t'"), "il": ("se ", "s'"), "ils": ("se ", "s'"),
        "nous": ("nous ",), "vous": ("vous ",)}


def unreflexive(form: str, person: str) -> str:
    for p in REFL[person]:
        if form.startswith(p):
            return form[len(p):]
    return form


def cross_check(verbs: dict) -> list[dict]:
    bases = {}
    for name in verbs:
        base = name[3:] if name.startswith("se ") else name[2:] if name.startswith("s'") else name
        bases[name] = base
    ml = run_mlconjug(sorted(set(bases.values())))
    out = []
    for name, rec in verbs.items():
        m = ml.get(bases[name], {})
        for t in SIMPLE_TENSES:
            for p in PERSONS:
                ref = rec["forms"][t][p]
                alts = [ref] + rec.get("variants", {}).get(t, {}).get(p, [])
                if rec["pronominal"]:
                    alts = [unreflexive(a, p) for a in alts]
                got = m.get(t, {}).get(p)
                got = norm(got) if got else None
                if got is None or got not in alts:
                    out.append({"verb": name, "tense": t, "person": p,
                                "verbecc": rec["forms"][t][p], "mlconjug3": got})
    out.sort(key=lambda d: (d["verb"], d["tense"], PERSONS.index(d["person"])))
    return out


def main() -> None:
    logging.disable(logging.CRITICAL)
    from verbecc import CompleteConjugator, LangCodeISO639_1

    conj = CompleteConjugator(LangCodeISO639_1.fr)
    rows = load_lexique()
    nouns = build_nouns(rows)

    chosen, skipped = select_verbs(rows, conj)
    names = sorted(set(chosen) | set(CURATED))
    verbs, dropped = {}, []
    for n in names:
        rec = conjugate_verb(conj, n)
        if rec is None:
            dropped.append(n)
            continue
        verbs[n] = rec
    missing = [c for c in CURATED if c not in verbs]
    assert not missing, f"curated verbs failed: {missing}"

    for verb, tense, person, expected in ASSERTIONS:
        got = verbs[verb]["forms"][tense][person]
        assert got == expected, f"ASSERTION FAILED {verb} {tense} {person}: {got!r} != {expected!r}"

    dis = cross_check(verbs)
    conj_out = {
        "schema_version": 1,
        "source": conjugation_source(),
        "persons": PERSONS,
        "verbs": verbs,
    }
    dump_json(OUT / "nouns.json", nouns, sort_keys=False)
    dump_json(OUT / "conjugations.json", conj_out)
    (OUT / "conjugation_disagreements.yaml").write_text(
        yaml.safe_dump(dis, allow_unicode=True, sort_keys=True, width=1000, default_flow_style=False),
        encoding="utf-8",
    )
    print(f"nouns: {len(nouns['nouns'])}")
    print(f"verbs: {len(verbs)} (inferred: {sum(v['inferred'] for v in verbs.values())}; "
          f"skipped unknown/defective: {len(skipped)+len(dropped)})")
    print(f"disagreements: {len(dis)}")
    if dropped:
        print("defective (dropped):", ", ".join(sorted(dropped)))


if __name__ == "__main__":
    main()
