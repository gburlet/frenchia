# ADR 0004: Contextual tutor (grounding, streaming, warm-up)

- Status: accepted (2026-10-24)
- Code: `backend/tutor/`, `frontend/src/features/tutor/`. Contract: `docs/api-tutor.md`.

## Decisions

- **Context comes from IDs, resolved on the server.** The browser sends
  `{lesson_id, exercise_revision_id, attempt_id}`, and the server builds the context:
  - the lesson excerpt;
  - the exercise, with its answer key;
  - the learner's answer and the grader's feedback, flagged as fallible;
  - recurring mistakes and weak topics;
  - matching Québec lexicon entries.

  Ownership is checked: only your own attempts can be used. Nothing is pasted, and the size is bounded.
- **Deterministic grounding against hallucination.** In the first live test Gemma said « aller » takes
  avoir. The context now carries **verified verb facts** from the conjugation reference
  (auxiliary, past participle, key forms) for the verbs in the exercise, the answer and the question,
  plus the Québec lexicon. The prompt tells the model these facts are authoritative.
- **Hints, not answers,** when the exercise hasn't been attempted yet.
- **Streaming.** Server-sent events come from native async Django views over the OpenAI-compatible stream.
  A stopped or failed reply keeps its partial text (status `stopped` or `error`) and can be retried.
- **Warm-up.** A cold load of Gemma, which also loads its vision and audio projectors, took about 40 s before the
  first token. Two changes fix it:
  - Ollama keep-alive went from 30 min to 2 h.
  - The app pings `POST /api/llm/warm` when it opens. The server throttles the ping, and it is fire-and-forget.

  A first question after a cold start then got its first token in about 4 s.

## Evidence

`manage.py tutor_eval < evals/french/tutor.yaml` runs 10 curated scenarios through the production prompt and
grounding. They cover auxiliaries, verb + preposition, countries, Québec usage, tense choice,
pronominal agreement, the subjunctive, hint-only, and « -tu ». Each scenario has must and must-not patterns.

| Prompt | Pass | First token (median, warm) |
|---|---|---|
| tutor-2 (grounded) | 10/10 | 1.6 s |

## Consequences

- The tutor and grading share one Ollama slot, so content generation in the background slows both.
- Future spoken conversation can reuse `TutorThread`/`TutorMessage`, which are generic (role, content, context), the
  streaming provider, and the TTS service.
