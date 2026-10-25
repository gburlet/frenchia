# Content authoring

Learning content is **version-controlled YAML** in `content/`. The **local LLM writes it** and
you review it. Claude wrote the software and the curriculum skeleton, but no lesson prose.

```
content/
├── curriculum/{a1,a2,b1,b2}.yaml  units → lesson outlines (ids, order, objectives, topics, Québec angle)
├── grammar/topics.yaml            grammar topics: the unit of mastery tracking
├── lessons/<level>/<id>.yaml      published lessons (sections + exercises)
├── drafts/<level>/<id>.job-N.yaml generated drafts awaiting review (not imported)
├── reference/                     deterministic data: conjugations, noun genders, Québec lexicon
└── schemas/                       JSON Schema exported from backend/contentkit (editor validation)
```

The schemas live in `backend/contentkit/models.py` (Pydantic). They are the single source of truth for the files,
the importer and the LLM's structured output.

## Workflow

1. **Generate.** In Admin → Lessons, select lessons and run "Generate content with the local LLM".
   Alternatively, run `just content-generate a2-imparfait` (add `--sync` to watch it run). The worker calls Gemma
   once per section or exercise batch with a JSON schema. The calls are grounded in the lesson outline, the
   lesson so far and matching entries from `reference/quebec.yaml`.
2. **Automatic checks.** These run after every step, and any error is sent back to the LLM once for
   repair:
   - schema rules
   - verb forms in fill-in-the-blank answers against `reference/conjugations.json`
   - noun genders against Lexique
   - English text in French fields
   - Québec terms missing from the verified lexicon (warning)
   - repeated words after filling a blank
3. **External proof-reading (ADR 0003).** `just content-review-export` writes one self-contained
   prompt per job awaiting review to `content/drafts/review/job-N.prompt.txt`. A stronger model
   reads it and writes `job-N.findings.json` next to it. In practice that's a Claude Code Haiku
   subagent; anything that follows the JSON schema at the end of the prompt works. Then run
   `just content-review-import claude-haiku-5-5` (add `--revise` to queue a local-LLM revision
   from the findings straight away). Findings appear in Admin as suggestions and pre-fill the
   revision form. They are never applied automatically.
4. **Review.** Open Admin → Generation jobs. Each job shows a rendered preview, the validation report and a diff
   against the published version. Then choose one of:
   - **Approve & publish:** writes `content/lessons/<level>/<id>.yaml` with the next `content_version`, imports
     it and makes it live.
   - **Reject**, with notes.
   - **Request revision:** give notes and optional section/exercise ids. The local LLM revises those parts and
     a new job appears for review.
5. **Commit** the changed YAML with git. Nothing is committed automatically.

You can also edit lesson YAML by hand. Bump `content_version`, then run
`just content-import --publish`. A manual edit is detected because the content hash no longer matches
`provenance.generated_hash`. Approving a fresh generation over an edited file needs an explicit
"overwrite manual edits".

## Guarantees

- **Idempotent import:** the same id, version and content is a no-op. The same version with different
  content is refused until you bump the version. A version older than one already imported is refused.
- **History is never rewritten.** Every imported version is an immutable `LessonRevision`, and each
  exercise gets an immutable `ExerciseRevision`. Learner attempts point at those, so regeneration never
  changes what a past answer was graded against.
- **Rollback** with `just content-publish <lesson> --version N` (or the revision's Admin action).
  This only moves the "published" pointer.
- **Confined writes.** The LLM never touches the filesystem. `authoring/writer.py` derives every path from
  validated ids and refuses anything outside `content/`.

## Verb banks and vocabulary sets (Phase 6)

The Verb and Vocabulary Stations use two more kinds of generated content. Both go through the
same check → proof-read → publish loop, from the command line rather than Admin:

| Content | Outline (hand-written) | Generated file |
|---|---|---|
| Verb drill sets | `verbs/sets.yaml` (which verbs, suggested tenses) | none: sets are structure only |
| Verb banks | the reference verb + its sets' tenses | `verbs/bank/<verb>.yaml`: gloss, note, ~10–14 context sentences |
| Vocabulary sets | `vocabulary/themes.yaml` (scope, Québec angle, size) | `vocabulary/sets/<theme>.yaml` |

1. **Generate.** `just bank-generate verbs --set essentiels` (or a list of infinitives, or no
   argument for every set verb) and `just bank-generate vocab a1-hiver` (or `--level A2`). Drafts
   go to `content/drafts/{verbs,vocabulary}/`. Existing drafts and published files are skipped
   unless you pass `--force`; a regenerated file gets the next `content_version`.
   - Verb banks: the conjugation reference supplies the exact form for each (tense, person) slot
     and Gemma only writes a sentence around it. A sentence is kept only if the form, or a
     correctly agreed form (« est allée »), is in it. One repair round, then the slot is dropped.
     Region "qc" is derived from the verified lexicon, not from the model.
   - Vocabulary sets: articles are stripped, noun genders are corrected from Lexique, duplicates
     are dropped, and Québec claims not in `reference/quebec.yaml` are downgraded to "common".
2. **Proof-read.** `just bank-review-export` writes `drafts/review/<kind>-<id>.prompt.txt`.
   A Claude Code Haiku subagent writes `<kind>-<id>.findings.json` next to each one (same schema
   as for lessons). Then run `just bank-review-import claude-haiku-5-5 --revise`:
   - an item with an error is rewritten by Gemma using the finding, and dropped if the rewrite
     still fails the checks;
   - without `--revise`, flagged items are dropped;
   - a flagged note is removed;
   - a draft whose review needed no rewrite is marked `provenance.reviewed_by`. Rewritten drafts
     go back for another round (`bank-review-export` again).
3. **Publish.** `just bank-promote` (optionally with ids) moves reviewed, error-free drafts into
   `content/` and imports them. Then commit the YAML.

What the deterministic checks catch, because Gemma does these and Haiku misses some:

- a sentence translation that is only the gloss ("Choose"), runs on into the prompt's slot list
  (« 2. Présent (tu) … »), lists alternatives (" / ") or leaks the next JSON key;
- a je/tu/nous/vous sentence with no subject: « Choisissez… » in a present-tense slot is an
  imperative;
- a pronominal nous/vous form without its subject: « Nous levons » for *se lever* needs
  « Nous nous levons »;
- notes that describe the edit ("The original example was replaced…"), or that give a
  Québec/France equivalent on a word that isn't Québec usage.

Québec lexicon entries can carry a `gender`, which overrides Lexique (« un party »). Only
entries the theme or the verb actually mentions go into a prompt: a generic sample ended up in
every set and sentence.

Vocabulary from lessons needs none of this. Every published lesson's vocabulary sections and
reading glossaries become a "From your lessons" set automatically, on import and on publish.

Imported vocabulary follows the lesson rules: an unchanged version is a no-op, and changed
content needs a version bump. Words are updated in place so learners keep their review history.
Words dropped from a set are retired, never deleted.

## Prompts

Prompts live in `backend/authoring/prompts.py` and each has a version. Bump the version whenever
the wording changes. Jobs and lesson provenance record the versions used.
