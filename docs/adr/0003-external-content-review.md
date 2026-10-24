# ADR 0003: Claude Haiku as an optional external reviewer of generated content

- Status: accepted (2026-10-24)
- Evidence: `evals/results/2026-10-24-haiku-subagent/` (Haiku ran as a Claude Code subagent on
  blinded prompts exported by `evals/blind.py` and `evals/lesson_review.py`).

## Context

Gemma 4 12B generates the lessons locally (ADR 0002). The first real lesson passed every
deterministic check but still contained a grammar error (« Elle a parlé son ami »), two
multiple-choice questions with two correct options, and wrong or misplaced Québec claims. The question was
whether a stronger model should proof-read generated content before human review.

## Results

**Same 85 blinded prompts** as the Gemma bake-off (judge v2 with Québec grounding):

| | Judge | Category hit | Québec accept | Grammar | Québec MCQ | Conjugation | Genders |
|---|---|---|---|---|---|---|---|
| gemma4:12b-it-qat | 0.97 | 0.96 | 0.75 | 0.93 | 1.00 | 1.00 | 1.00 |
| Claude Haiku 5.5 | 0.97 | **1.00** | **1.00** | **1.00** | 1.00 | 1.00 | 1.00 |

Haiku's only judging miss was demanding a space before « ! » (a France typography rule).

**Reviewing the real Gemma lesson**, against 9 problems found by hand:

| Reviewer | Problems found | False "errors" on the cleaned-up revision |
|---|---|---|
| Gemma reviewing itself | 5 / 9 (missed « parlé son ami » and one bad MCQ) | several |
| Claude Haiku 5.5 | **8 / 9** (missed only an odd but harmless "pitfall") | none (3 correctly labelled suggestions, one of which exposed a real revision bug) |

## Decision

- Use **Claude Haiku 5.5 as an optional external reviewer** of generated lessons. It runs between
  local generation and the learner's review in Admin.
- Its findings are **suggestions shown in the review screen**. They are never applied
  automatically, and they never decide anything on their own.
- The app's runtime stays fully local. Review is an authoring-time step that you run on demand. It is
  the only place a paid or remote model is used, and only on generated course text, never on
  learner data.

Cost: about 4K tokens per lesson. Through the API that is about $0.005 per lesson, or about $0.60 for
all 120 A1–B2 lessons. Through Claude Code Haiku subagents, it comes out of the plan's usage instead,
with roughly 30K tokens of per-agent overhead; batching several lessons per agent amortizes it.

## Consequences

- The reviewer is pluggable: anything that produces the `REVIEW_SCHEMA` JSON (API, subagent, or a
  future local model) can attach findings to a generation job.
- The eval tools (`blind.py`, `lesson_review.py`) let any future reviewer or generator be compared
  on the same prompts without leaking answers.
