# ADR 0005: Verb and Vocabulary Stations

- Status: accepted
- Date: 2026-10-24

## Context

Phase 6 adds conjugation drills and vocabulary flashcards. The plan's acceptance criteria are
that drills grade with no LLM and that FSRS due queues persist. The learner is A2, aiming for
B2, and Québec-first.

## Decisions

### Conjugation grading is deterministic
- `contentkit/conjugation.py` grades typed forms against `reference/conjugations.json`
  (verbecc, cross-checked with mlconjug3). It does this in a few milliseconds, with no model
  call.
- Normalisation:
  - the subject pronoun is optional, as is `que` in the subjunctive;
  - straight and curly apostrophes, case and trailing punctuation are ignored;
  - spelling variants are accepted (*je paye / je paie*).
- Agreement:
  - Compound tenses with être accept an agreed participle (*suis allée*). Writing *elle*
    narrows this to feminine agreement.
  - Verbs that take both auxiliaries also accept avoir (*j'ai sorti*).
- A context sentence fixes the agreement it needs (*Marie ___ (partir)* → *est partie*).
- Wrong answers are diagnosed by search, not guessed. The diagnosis is the first of these that
  fits:
  1. accents only;
  2. the infinitive;
  3. another person's form;
  4. another tense's form;
  5. the wrong auxiliary;
  6. a wrong auxiliary form;
  7. a wrong participle;
  8. a missing agreement;
  9. a near miss (Levenshtein distance ≤ 2).

  The explanations are written by code, so they are always true.
- Futur proche (*aller* + infinitive) is derived, including the reflexive pronoun
  (*je vais m'asseoir*). It is an A1 tense in everyday Québec speech.
- Passé simple appears in the tables but is never drilled.

### Context sentences are generated around known forms
- The model is never asked to conjugate. For each (tense, person) slot, the prompt gives the
  exact reference form, and Gemma writes a sentence around it.
- A sentence is kept only if it contains an accepted form for that slot. The form is extracted
  from the sentence itself, so agreement is whatever the sentence needs.
- Sentences are then proof-read by a Haiku subagent (ADR 0003) before they are published to
  `content/verbs/bank/`.
- Banks are file-backed reference content, like the conjugation tables. They are read through
  an mtime-keyed in-process cache (`curriculum/content.py`), not projected into the database.
- Each attempt stores a snapshot of its sentence, so later edits never change what a past
  answer was graded against.
- This replaces the plan's `Verb`/`VerbForm` tables. The reference is immutable, versioned
  data, and a projection would only duplicate it.

### Vocabulary: database projection with in-place lexemes
- Themed sets are generated per `vocabulary/themes.yaml` outline, with the same proof-reading,
  and imported with the lesson versioning rules.
- Published lessons' vocabulary becomes "lesson sets" automatically.
- `Lexeme` rows are updated in place, so learners keep their scheduling when a gloss is
  corrected. Dropped words are retired, never deleted.
- Adding a set creates two cards per word: recognition (FR→EN) and recall (EN→FR). Words
  already in the deck from another set are skipped.

### FSRS scheduling
- Scheduling uses `fsrs` 6.3.2 (MIT) with 90% desired retention, 1 min and 10 min learning
  steps, and fuzzing. The card state is stored as `Card.to_dict()` JSON next to an indexed
  `due` column.
- Interval previews on the rating buttons use an unfuzzed scheduler, so the labels are stable.
- Each learner gets a daily limit of new cards (`LearnerProfile.daily_new_cards`, default 15).
  A word's recall card unlocks only after its recognition card has been seen.
- Recall answers are checked deterministically:
  - an accents-only difference counts as accent;
  - a missing article counts as article;
  - le/la swapped counts as gender;
  - missing *se* on a reflexive verb is treated like a missing article;
  - each result maps to a suggested rating, which the learner can change.

### Québec lexicon expansion
- `reference/quebec.yaml` grew from 19 to 64 entries. The new entries cover clothing (*bas*,
  *chandail*, *mitaines*), winter (*poudrerie*, *sloche*, *banc de neige*), money (*piasse*,
  *cenne*), everyday verbs (*jaser*, *pogner*, *chialer*, *achaler*, *capoter*, *pelleter*) and
  expressions (*pas pire*, *c'est correct*, *ça me tente*).
- These entries ground generation and gate "qc" labels. They are marked as pending the
  learner's review.

## Consequences

- Drills and flashcards work while the LLM is down or busy.
- New verbs need a reference rebuild (`just build-reference`; 12 Québec and everyday verbs were
  added this way). New sentences need a generate → review → promote round.
- Generating banks occupies the single Ollama slot (about 45 s per verb and 2.5 min per
  vocabulary set). Phase 7's "pause generation while the learner is active" also covers this.
