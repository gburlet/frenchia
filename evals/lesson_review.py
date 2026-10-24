#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1", "pyyaml==6.0.3", "jsonschema==4.26.0", "anthropic==2.3.0"]
# ///
"""Can a model catch the French problems in a generated lesson? Scores recall against the
hand-made ground truth in french/lesson_review.yaml and prints unmatched findings for review.

    uv run evals/lesson_review.py --provider anthropic claude-haiku-5-5
    uv run evals/lesson_review.py gemma4:12b-it-qat          # local baseline
    uv run evals/lesson_review.py x --export DIR              # prompts for an external reviewer
    uv run evals/lesson_review.py claude-haiku-5-5 --findings DIR   # score its <n>.json answers
"""

import argparse
import json
import re
from pathlib import Path
from typing import Any

import jsonschema

import yaml

from bakeoff import CASES, AnthropicClient, Client

CATEGORIES = ["grammar", "spelling", "meaning", "translation", "exercise_design", "quebec_usage",
              "consistency", "other"]
REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "item_id": {"type": "string"},
            "severity": {"type": "string", "enum": ["error", "suggestion"]},
            "category": {"type": "string", "enum": CATEGORIES},
            "problem": {"type": "string"},
            "suggested_fix": {"type": "string"},
        },
        "required": ["item_id", "severity", "category", "problem", "suggested_fix"],
        "additionalProperties": False,
    }}},
    "required": ["issues"],
    "additionalProperties": False,
}
PROMPT = """\
You are reviewing a lesson that a smaller model generated for an English-speaking adult learning \
Québec French (CEFR {level}). The learner will study it and be graded against its answer keys, so \
errors teach mistakes. Review it as an expert teacher and report every real problem:
- every French sentence: grammar, agreement, prepositions (parler à…), articles, accents, \
naturalness;
- translations in both directions;
- answer keys: each fill-in-the-blank must be fully correct once filled; each multiple-choice \
question must have exactly one correct option (an option that is the right answer with different \
punctuation is also correct);
- Québec usage: Québec usage is the default (déjeuner = breakfast, dîner = lunch, souper = supper; \
« la fin de semaine », not « le week-end »). Flag claims about Québec usage that are wrong or \
misplaced, but only when you are certain;
- consistency: notes must be about the sentence they're attached to; glossary words are written \
without articles; explanations must describe mistakes learners really make.
Use item_id = the id of the section or exercise. severity 'error' = must fix; 'suggestion' = could \
be better. Do not report style preferences as errors, and do not invent problems.

Verified Québec usage:
{lexicon}

Lesson (JSON):
{lesson}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("model")
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    ap.add_argument("--base", default="http://127.0.0.1:11435")
    ap.add_argument("--export", type=Path, help="write prompt-<n>.txt + schema.json, call nothing")
    ap.add_argument("--findings", type=Path, help="score findings-<n>.json written by an external model")
    args = ap.parse_args()
    client: Any = None
    if not (args.export or args.findings):
        client = AnthropicClient(args.model) if args.provider == "anthropic" else Client(args.base, args.model)
    if args.export:
        args.export.mkdir(parents=True, exist_ok=True)
        (args.export / "schema.json").write_text(json.dumps(REVIEW_SCHEMA, indent=1))
    lexicon = yaml.safe_load((CASES.parent.parent / "content" / "reference" / "quebec.yaml").read_text())
    lexicon_text = "\n".join(f"- {e['term']}: {e['meaning']} (France: {e['france']})" for e in lexicon)
    total_hits = total_expected = 0
    for n, case in enumerate(yaml.safe_load((CASES / "lesson_review.yaml").read_text())):
        lesson = json.loads((CASES / case["lesson"]).read_text())
        prompt = PROMPT.format(level=lesson["level"], lexicon=lexicon_text,
                               lesson=json.dumps(lesson, ensure_ascii=False, indent=1))
        if args.export:
            (args.export / f"prompt-{n}.txt").write_text(prompt)
            continue
        if args.findings:
            raw = (args.findings / f"findings-{n}.json").read_text()
            obj, dt, toks = json.loads(raw), 0.0, None
            jsonschema.validate(obj, REVIEW_SCHEMA)
        else:
            obj, dt, toks, raw = client.structured(prompt, REVIEW_SCHEMA, 4000)
        print(f"\n=== {case['lesson']}  ({dt:.0f}s, {toks} output tokens)")
        if obj is None:
            print("  invalid output:", raw[:300])
            continue
        issues = obj["issues"]
        matched: set[int] = set()
        for exp in case["expected"]:
            hit = next((i for i, f in enumerate(issues) if f["item_id"] == exp["item"] and any(
                re.search(re.escape(k), f["problem"] + " " + f["suggested_fix"], re.I) for k in exp["keywords"])), None)
            total_expected += 1
            if hit is not None:
                matched.add(hit)
                total_hits += 1
            print(f"  {'✓' if hit is not None else '✗'} {exp['id']:18s} {exp['what']}")
        extras = [f for i, f in enumerate(issues) if i not in matched]
        if extras:
            print(f"  unmatched findings ({len(extras)}): classify by hand")
            for f in extras:
                print(f"    - [{f['severity']}/{f['category']}] {f['item_id']}: {f['problem']} → {f['suggested_fix']}")
    if args.export:
        print(f"wrote prompts and schema to {args.export}")
        return
    print(f"\nRecall: {total_hits}/{total_expected}")
    if isinstance(client, AnthropicClient):
        print(f"Tokens in {client.input_tokens}, out {client.output_tokens}: ${client.cost_usd:.4f}")


if __name__ == "__main__":
    main()
