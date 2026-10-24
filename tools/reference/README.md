# Reference data builder

Builds the deterministic French reference data used to validate LLM-generated lessons
(the app never asks an LLM whether a conjugation or gender is correct).

## Rebuild

```
uv run tools/reference/build_reference.py
```

Needs `uv` and network on first run (Lexique zip is cached in `tools/reference/.cache/`, git-ignored).
Takes about a minute (most of it resolving/running the mlconjug3 helper and verbecc). Output is
deterministic and idempotent (stable JSON, `ensure_ascii=False`, indent 1, sorted keys).

The script asserts 12 known forms (e.g. aller/ils = vont, se lever imperative tu = lève-toi) before writing
anything, and fails loudly on mismatch.

mlconjug3 4.0.1 cannot live in the same environment as verbecc 2.0.3 (numpy pin conflict, and its pickled
model only loads on Python 3.10), so `mlconjug_dump.py` (its own PEP 723 script) is run as a subprocess via `uv run`.

## Outputs (`content/reference/`)

- `nouns.json`: top 15,000 Lexique 3.83 common-noun (`NOM`) lemmas ordered by `freqlemfilms2` (lemma frequency in
  film subtitles per million; ties alphabetical; this dict is the one deliberately not key-sorted so order = rank).
  `gender` is `m`/`f` if the gendered rows agree, `mf` if both occur or Lexique leaves gender blank (epicene or
  meaning-dependent: élève, livre, tour; this also catches a few nouns whose gender Lexique simply doesn't record).
- `conjugations.json`: ~320 verbs (top 300 Lexique `VER` lemmas that verbecc knows and fully conjugates, plus the
  curated pronominal/Québec set). Per verb: `group`, `auxiliary` (`avoir`/`être`/`both`), `pronominal`, `inferred`,
  participles, `forms` for 12 tense keys, and optional `variants` (alternate valid forms, e.g. assois/assieds).
  Forms have no subject pronoun and no "que"; pronominals keep the reflexive pronoun; compound tenses include the
  auxiliary; masculine agreement (plural with être). `imperatif.present` is `{}` for verbs with no imperative (pouvoir).
  `inferred: true` = unknown to verbecc, conjugated with its regular -er (`aim:er`) template (placoter, pogner).
  For `both` verbs, compound forms use verbecc's default auxiliary; the curated list is `BOTH_AUX` in the script.
- `conjugation_disagreements.yaml`: simple-tense forms where mlconjug3 differs from verbecc (verbecc stays the
  reference). Mapping: indicatif.present/imparfait/futur_simple/passe_simple, conditionnel.present, subjonctif.present
  <- mlconjug3 Présent/Imparfait/Futur/Passé Simple/Présent/Présent. Compound tenses and the imperative are not
  compared (mlconjug3 lacks them or returns only one form). Pronominals are compared on the base verb with the
  reflexive stripped. A match against any verbecc variant counts as agreement.
- `ATTRIBUTION.md`: licences and citations.

Defective verbs (falloir, pleuvoir, foutre) are skipped from the frequency list.
