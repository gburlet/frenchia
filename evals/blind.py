#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1", "pyyaml==6.0.3", "jsonschema==4.26.0", "anthropic==2.3.0"]
# ///
"""Evaluate a model that can't be called from here (e.g. a Claude subagent) on the bake-off
cases, without leaking the answers.

    uv run evals/blind.py export questions.json        # prompts + schemas, no ground truth
    # ... the external model writes answers.json: [{"i": 0, "output": {...} | "text"}, ...]
    uv run evals/blind.py score questions.json answers.json --model claude-haiku-5-5

Both steps run the exact task code of bakeoff.py (same prompts, same scoring) through a
recording / replaying client, so results are directly comparable with local models.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import jsonschema
import yaml

from bakeoff import CASES, SYSTEM, run_conj, run_explain, run_genders, run_judge_v2, run_mcq, summarize

TASKS = ["judge", "grammar", "quebec", "conjugation", "genders", "explain"]


class RecordingClient:
    def __init__(self) -> None:
        self.model = "recording"
        self.items: list[dict[str, Any]] = []

    def chat(self, user: str, schema: dict | None = None, max_tokens: int = 700) -> tuple[str, float, int | None]:
        self.items.append({"i": len(self.items), "prompt": user, "schema": schema})
        return "", 0.0, 0

    def structured(self, user: str, schema: dict, max_tokens: int = 700) -> tuple[dict | None, float, int | None, str]:
        self.chat(user, schema, max_tokens)
        return None, 0.0, 0, ""


class ReplayClient:
    def __init__(self, model: str, answers: dict[int, Any]) -> None:
        self.model, self.answers, self.n = model, answers, 0

    def chat(self, user: str, schema: dict | None = None, max_tokens: int = 700) -> tuple[str, float, int | None]:
        out = self.answers.get(self.n, "")
        self.n += 1
        return (out if isinstance(out, str) else json.dumps(out, ensure_ascii=False)), 0.0, None

    def structured(self, user: str, schema: dict, max_tokens: int = 700) -> tuple[dict | None, float, int | None, str]:
        text, dt, toks = self.chat(user, schema, max_tokens)
        try:
            obj = json.loads(text)
            jsonschema.validate(obj, schema)
            return obj, dt, toks, text
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return None, dt, toks, text


def run_all(c: Any) -> list[Any]:
    judge = yaml.safe_load((CASES / "judge.yaml").read_text())
    grammar = yaml.safe_load((CASES / "grammar.yaml").read_text())
    quebec = yaml.safe_load((CASES / "quebec.yaml").read_text())
    gen = yaml.safe_load((CASES / "generation.yaml").read_text())
    explain = yaml.safe_load((CASES / "explain.yaml").read_text())
    lexicon = yaml.safe_load((CASES / "quebec_lexicon_seed.yaml").read_text())
    return [
        *run_judge_v2(c, judge, lexicon),
        *run_mcq(c, grammar, "grammar"),
        *run_mcq(c, quebec, "quebec"),
        *run_conj(c, gen["conjugation"]),
        *run_genders(c, gen["genders"]),
        *run_explain(c, explain),
    ]


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("export")
    ex.add_argument("out", type=Path)
    sc = sub.add_parser("score")
    sc.add_argument("questions", type=Path)
    sc.add_argument("answers", type=Path)
    sc.add_argument("--model", required=True)
    args = ap.parse_args()

    if args.cmd == "export":
        rec = RecordingClient()
        run_all(rec)
        args.out.write_text(json.dumps({"system": SYSTEM, "items": rec.items}, ensure_ascii=False, indent=1))
        print(f"wrote {len(rec.items)} prompts to {args.out}")
        return

    expected = len(json.loads(args.questions.read_text())["items"])
    answers = {a["i"]: a["output"] for a in json.loads(args.answers.read_text())}
    missing = sorted(set(range(expected)) - set(answers))
    if missing:
        print(f"warning: {len(missing)} answers missing: {missing[:20]}", file=sys.stderr)
    results = run_all(ReplayClient(args.model, answers))
    summary = summarize(args.model, results, {}, {})
    keys = ["judge_score", "judge_category_hit", "judge_quebec_accept", "grammar_score", "quebec_score",
            "conjugation_score", "genders_score", "explain_score", "json_valid_rate"]
    print(json.dumps({k: summary.get(k) for k in keys}, indent=1))
    for r in results:
        if not r.ok and r.task != "explain":
            print(f"  MISS {r.task}/{r.case_id}: {json.dumps(r.detail, ensure_ascii=False)[:220]}")


if __name__ == "__main__":
    main()
