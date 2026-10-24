# ADR 0002: Local LLM model and judging approach

- Status: accepted (2026-10-24)
- Evidence: `evals/results/2026-10-24-*` (harness and cases in `evals/`)

## Context

Phase 2 bake-off: 89 hand-written French/Québec cases. Every candidate ran through the app's own
path (Ollama 0.40.11, OpenAI-compatible API, JSON-schema constrained output, thinking off,
temperature 0) on the M2 Pro (16 GB), with other Docker stacks stopped.

| Model (Ollama tag) | Judge | Grammar | Québec | Conjugation | Genders | JSON valid | Judge p50 / p90 | Decode | Resident |
|---|---|---|---|---|---|---|---|---|---|
| **gemma4:12b-it-qat** | **0.85** | **0.93** | **1.00** | **1.00** | 1.00 | **100%** | 7.0 / 9.0 s | 22 tok/s | 7.7 GB |
| qwen3.5:9b | 0.74 | 0.93 | 0.86 | 0.75 | 1.00 | 98.8% | 5.1 / 6.4 s | 24 tok/s | 7.8 GB |
| ministral-3:8b | 0.74 | 0.80 | 0.93 | 0.90 | 1.00 | 100% | 5.5 / 7.7 s | 28 tok/s | 6.2 GB |
| qwen3.5:4b | 0.77 | 0.67 | 0.64 | 0.80 | 1.00 | 97.5% | 3.5 / 4.5 s | 45 tok/s | 4.1 GB |

Notable failures:
- **Gemma (judge v1):**
  - Accepted "un vieux homme" and "en Canada" as correct, with confident wrong explanations.
  - Marked clear tense and article errors "acceptable".
  - Said Québécois use "dîner" for both lunch and supper.
  - Chose "se sont rencontré" (no agreement).
- **Qwen 3.5 9B:** said Québec *souper* means breakfast, rejected "Tu viens-tu ?" as a spelling error, and dropped accents in conjugations.

### Judge v2 experiment (Gemma only)

What changed in v2:
- The model lists errors, each with a severity (`error`/`minor`), and **the verdict is computed in code**.
- The prompt adds a checklist of standard A1–B1 error classes (agreement, vieil/bel/nouvel,
  articles, country/city prepositions, auxiliaries, tense choice, pronoun order, negation,
  meaning-bearing accents).
- Matching Québec lexicon entries can be injected as grounding.

| Variant | Verdict accuracy | Category hit | p50 / p90 latency | Median output tokens |
|---|---|---|---|---|
| v1 | 0.85 | 0.84 | 7.0 / 9.0 s | 111 |
| v2 | 0.97 | 0.96 | 13.8 / 17.5 s | ~215 |
| v2 + Québec grounding | 0.97 | 0.96 | 13.5 / 16.3 s | 217 |

The one remaining v2 miss is « On soupe à six heures ». Gemma parses *soupe* as the noun, even
with the grounding entry. Latency is entirely output-bound (about 0.061 s per generated token in both
variants).

Memory: with Gemma resident, free memory fell to 13% (swap grew from 13.6 to 22.7 GB, mostly
inactive pages pushed out). Once the model was unloaded, free memory was back at 72%. This is
workable only with the other Docker stacks stopped.

## Decision

1. **Default model: `gemma4:12b-it-qat`.** It clearly leads on Québec usage, conjugation and
   judging, and it never produced invalid JSON. It is set via `INFERENCE_LLM_MODEL`.
   `qwen3.5:4b` stays available as an emergency fast tier, but it is not used: its Québec and
   grammar knowledge is too weak for teaching.
2. **Judging uses the v2 design.** Errors carry a severity, the verdict is computed in code, and
   the prompt includes the error checklist and Québec lexicon grounding. The grounding did not
   change the score on this set, but it is cheap and it targets the hallucination class we
   observed.
3. **LLM feedback is never the only safeguard.**
   - Exact or accepted-answer matches are graded deterministically.
   - Conjugation, gender and Québec claims are checked against reference data where possible.
   - The UI labels feedback as AI-generated and offers "I think I'm right" disputes, which feed the
     curated accepted answers.

## Consequences

- **Phase 4 must bring judging latency down** (target p50 under 8 s). Planned levers:
  - Cap explanation lengths in the schema and prompt.
  - Move long explanations to the on-demand tutor.
  - Stream the evaluation to the UI.
  - Short-circuit accepted answers.
- **Pronominal and verb-form ambiguity** (*on soupe*) needs conjugated forms in lexicon entries and
  the dispute flow.
- **Upgrades are re-checked.** Any model or Ollama upgrade must re-run
  `uv run evals/bakeoff.py <model>` and be compared against these numbers.

## Addendum (2026-10-24): production grader prompt

Measured with `manage.py grader_eval` on the 39 judge cases. This is the real grading code: deterministic
short-circuits, Québec lexicon grounding, and dropping of hallucinated spans.

| Prompt | Verdicts | Categories | LLM p50 / p90 | Change |
|---|---|---|---|---|
| judge-3 | 38/39 | 25/25 | 8.5 / 10.4 s | v2 design with the lexicon, under 20-word explanations and a model-written summary |
| judge-4 | 34/39 | 23/25 | 7.0 / 9.2 s | instructions moved into the system message (cache-friendly), no summary |
| **judge-5** | **39/39** | **25/25** | **7.9 / 9.9 s** | judge-3 layout, no model summary (written in code), under 12-word explanations |

Generation dominates latency: about 131 output tokens at about 21 tok/s, against about 0.2 s of cached prompt
processing. Shorter output is the lever. Gemma follows instructions placed after the case in the
user turn noticeably better than instructions in the system message. Adding conjugated forms
(« on soupe ») to the Québec lexicon fixed the remaining Québec judging miss.
