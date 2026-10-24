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

## Prompts

Prompts live in `backend/authoring/prompts.py` and each has a version. Bump the version whenever
the wording changes. Jobs and lesson provenance record the versions used.
