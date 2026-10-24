# LLM evals

A curated French and Québec eval set, plus a bake-off harness. Use them to choose the local LLM and to
re-check it before any model or runtime upgrade. The ground truth is hand-written. We never
ask the LLM to grade its own output.

## Cases (`french/`)

| File | What it measures | Scoring |
|---|---|---|
| `judge.yaml` (39) | Judging learner translations: gender and agreement, tense choice, pronoun placement, articles and partitives, prepositions, auxiliaries, negation, accents, alternative correct answers, **Québec variants against France references**, FR→EN meaning | Verdict (correct/acceptable vs incorrect) must match; for wrong answers, the error category must overlap |
| `grammar.yaml` (15) | Grammar knowledge, multiple choice | Exact option |
| `quebec.yaml` (14) | Québec usage (dîner/souper, magasiner, dépanneur, -tu, pantoute, …) | Exact option |
| `generation.yaml` | Conjugation tables (10), noun genders (16 nouns), open generation (fill-in-the-blank, translation items) | Exact forms and genders; structural checks for open items, whose output is kept for human review |
| `explain.yaml` (6) | Short grammar explanations | Concept rubric (regex groups); text kept for review |

## Running

```bash
just start   # or at least: python3 -I scripts/native.py up llm
uv run evals/bakeoff.py gemma4:12b-it-qat qwen3.5:9b --out evals/results/<name>
```

It calls Ollama's OpenAI-compatible endpoint with the same options as the app: JSON-schema
constrained output, `reasoning_effort: none`, temperature 0. For each model it records:
- the score per task and JSON validity
- judging latency (p50 and p90)
- decode and prefill speed, load time and resident size
- swap and free memory before and after

Each model is unloaded before the next one starts. Run it on an otherwise idle machine, with
other Docker stacks stopped and no TTS work, or the latency figures are meaningless.
