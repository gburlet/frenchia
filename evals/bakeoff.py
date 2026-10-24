#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx==0.28.1", "pyyaml==6.0.3", "jsonschema==4.26.0", "anthropic==2.3.0"]
# ///
"""LLM bake-off for Frenchia: French/Québec quality, JSON reliability, latency, memory.

Uses the same path as the app: Ollama's OpenAI-compatible /v1/chat/completions with
response_format=json_schema (grammar-constrained) and reasoning_effort="none".

    uv run evals/bakeoff.py gemma4:12b-it-qat qwen3.5:9b

`--provider anthropic` instead runs Claude models through the Anthropic API (structured
outputs via output_config.format; adaptive thinking at the model's default effort) and
records token usage and cost. Needs ANTHROPIC_API_KEY (or another SDK credential source).

    uv run evals/bakeoff.py --provider anthropic claude-haiku-5-5
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
import jsonschema
import yaml

HERE = Path(__file__).parent
CASES = HERE / "french"

SYSTEM = (
    "You are an expert French teacher for an English-speaking adult learner (currently A2, "
    "aiming for B2) who is learning Québec French. Québec usage is the default: accept Québec "
    "vocabulary and natural informal spoken forms as correct, mentioning register when "
    "relevant. Be precise and concise. Explanations are in English unless asked otherwise."
)

CATEGORIES = [
    "agreement", "article", "preposition", "tense", "conjugation", "auxiliary",
    "pronoun_placement", "negation", "word_order", "word_choice", "spelling_accents",
    "register", "missing_or_extra", "meaning",
]

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "acceptable", "incorrect"]},
        "categories": {"type": "array", "items": {"type": "string", "enum": CATEGORIES}},
        "corrected": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["verdict", "categories", "corrected", "explanation"],
    "additionalProperties": False,
}
JUDGE_V2_SCHEMA = {
    "type": "object",
    "properties": {
        "errors": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": CATEGORIES},
                "severity": {"type": "string", "enum": ["error", "minor"]},
                "span": {"type": "string"},
                "explanation": {"type": "string"},
            },
            "required": ["category", "severity", "span", "explanation"],
            "additionalProperties": False,
        }},
        "corrected": {"type": "string"},
        "register_note": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["errors", "corrected", "register_note", "explanation"],
    "additionalProperties": False,
}
CHECKLIST = (
    "Before concluding there are no errors, check each of: gender and number agreement (adjectives, "
    "past participles with être and preceding direct objects); special adjective forms before vowels "
    "(vieil, bel, nouvel, cet); articles (definite for general likes, partitive du/de la, de after "
    "negation, no article after être + profession); prepositions (à + city, en + feminine country, "
    "au/aux + masculine/plural country, verb + à/de); auxiliary (être verbs, pronominal verbs); tense "
    "choice (imparfait for habits/background, passé composé for completed events, depuis + présent); "
    "object pronoun placement and order; negation; accents that change meaning (a/à, ou/où)."
)


def lexicon_notes(lexicon: list[dict], *texts: str) -> str:
    hits = [e for e in lexicon if any(re.search(p, t, re.I) for p in e["match"] for t in texts)]
    if not hits:
        return ""
    lines = [f"- {e['term']}: {e['meaning']} (France: {e['france']}; register: {e['register']})" for e in hits]
    return "Verified Québec usage relevant here (treat as authoritative):\n" + "\n".join(lines) + "\n\n"


def run_judge_v2(c: Client, cases: list[dict], lexicon: list[dict] | None) -> list[Result]:
    out = []
    for k in cases:
        src_lang, tgt_lang = ("English", "French") if k["direction"] == "en_fr" else ("French", "English")
        notes = lexicon_notes(lexicon, k["source"], k["answer"], *k["references"]) if lexicon else ""
        prompt = (
            f"Evaluate a learner's translation ({k['level']} level) from {src_lang} to {tgt_lang}.\n"
            f"Source: {k['source']}\nReference translation(s): {json.dumps(k['references'], ensure_ascii=False)}\n"
            f"Learner answer: {k['answer']}\n\n{notes}"
            "The references are examples, not the only correct answers: other wordings, Québec usage and "
            "natural informal spoken forms are correct (mention register in register_note, not as an error).\n"
            "List every problem in the learner answer. severity 'error' = anything a teacher would mark "
            "wrong (grammar, agreement, article, preposition, tense, spelling or accent, wrong meaning); "
            "severity 'minor' = correct but slightly unnatural style. Do not invent errors. "
            f"{CHECKLIST}\nGive a corrected version (or the answer itself if it has no errors) and a short explanation."
        )
        obj, dt, toks, raw = c.structured(prompt, JUDGE_V2_SCHEMA, 900)
        if obj is None:
            out.append(Result(c.model, "judge", k["id"], False, 0, dt, False, toks, {"raw": raw[:400]}))
            continue
        severities = {e["severity"] for e in obj["errors"]}
        verdict = "incorrect" if "error" in severities else "acceptable" if severities else "correct"
        categories = sorted({e["category"] for e in obj["errors"] if e["severity"] == "error"})
        want_ok = k["expect"]["verdict"] == "correct"
        verdict_ok = (verdict != "incorrect") == want_ok
        cat_hit = None
        if not want_ok and k["expect"].get("categories"):
            cat_hit = bool(set(categories) & set(k["expect"]["categories"]))
        out.append(Result(c.model, "judge", k["id"], verdict_ok, float(verdict_ok), dt, True, toks,
                          {"verdict": verdict, "categories": categories, "category_hit": cat_hit,
                           "expected": k["expect"], "errors": obj["errors"], "corrected": obj["corrected"],
                           "register_note": obj["register_note"], "grounded": bool(notes)}))
    return out


MCQ_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string", "enum": ["a", "b", "c", "d"]},
        "explanation": {"type": "string"},
    },
    "required": ["answer", "explanation"],
    "additionalProperties": False,
}
PERSONS = ["je", "tu", "il", "nous", "vous", "ils"]
CONJ_SCHEMA = {
    "type": "object",
    "properties": {"forms": {
        "type": "object",
        "properties": {p: {"type": "string"} for p in PERSONS},
        "required": PERSONS,
        "additionalProperties": False,
    }},
    "required": ["forms"],
    "additionalProperties": False,
}
GENDER_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "noun": {"type": "string"},
            "gender": {"type": "string", "enum": ["m", "f"]},
            "indefinite_article": {"type": "string", "enum": ["un", "une"]},
        },
        "required": ["noun", "gender", "indefinite_article"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}
FILL_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "answer": {"type": "string"},
            "infinitive": {"type": "string"},
            "english": {"type": "string"},
        },
        "required": ["sentence", "answer", "infinitive", "english"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}
TRANS_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "english": {"type": "string"},
            "accepted_french": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["english", "accepted_french"],
        "additionalProperties": False,
    }}},
    "required": ["items"],
    "additionalProperties": False,
}
ETRE_VERBS = {
    "aller", "venir", "arriver", "partir", "entrer", "sortir", "monter", "descendre", "naître",
    "mourir", "rester", "tomber", "retourner", "revenir", "devenir", "rentrer", "passer",
    "repartir", "redescendre", "remonter", "ressortir", "parvenir", "intervenir",
}
ETRE_AUX = re.compile(r"\b(suis|es|est|sommes|êtes|sont)\b")


@dataclass
class Result:
    model: str
    task: str
    case_id: str
    ok: bool
    score: float
    latency_s: float
    json_valid: bool | None = None
    completion_tokens: int | None = None
    detail: dict[str, Any] = field(default_factory=dict)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFC", s).lower().replace("’", "'").strip()
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"^(que |qu')", "", s)


# USD per million tokens (input, output); prompts under 100K tokens.
PRICES = {"claude-haiku-5-5": (0.10, 0.50), "claude-sonnet-5-5": (2.0, 10.0), "claude-opus-5-5": (4.0, 20.0)}


class AnthropicClient:
    """Same interface as Client, backed by the Anthropic API."""

    def __init__(self, model: str) -> None:
        import anthropic

        self.model = model
        self.api = anthropic.Anthropic()
        self.input_tokens = 0
        self.output_tokens = 0

    @property
    def cost_usd(self) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (self.input_tokens * price_in + self.output_tokens * price_out) / 1e6

    def chat(self, user: str, schema: dict | None = None, max_tokens: int = 700) -> tuple[str, float, int | None]:
        params: dict[str, Any] = {
            "model": self.model,
            # Room for adaptive thinking on top of the visible answer.
            "max_tokens": max_tokens + 8000,
            "system": SYSTEM,
            "messages": [{"role": "user", "content": user}],
        }
        if schema:
            params["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
        t = time.perf_counter()
        response = self.api.messages.create(**params)
        dt = time.perf_counter() - t
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        if response.stop_reason == "refusal":
            return "", dt, response.usage.output_tokens
        text = next((b.text for b in response.content if b.type == "text"), "")
        return text, dt, response.usage.output_tokens

    def structured(self, user: str, schema: dict, max_tokens: int = 700) -> tuple[dict | None, float, int | None, str]:
        text, dt, toks = self.chat(user, schema, max_tokens)
        try:
            obj = json.loads(text)
            jsonschema.validate(obj, schema)
            return obj, dt, toks, text
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return None, dt, toks, text


class Client:
    def __init__(self, base: str, model: str) -> None:
        self.base, self.model = base.rstrip("/"), model
        self.http = httpx.Client(timeout=300)

    def chat(self, user: str, schema: dict | None = None, max_tokens: int = 700) -> tuple[str, float, int | None]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "reasoning_effort": "none",
        }
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "out", "schema": schema, "strict": True}}
        t = time.perf_counter()
        r = self.http.post(f"{self.base}/v1/chat/completions", json=body)
        r.raise_for_status()
        dt = time.perf_counter() - t
        data = r.json()
        return data["choices"][0]["message"]["content"] or "", dt, (data.get("usage") or {}).get("completion_tokens")

    def structured(self, user: str, schema: dict, max_tokens: int = 700) -> tuple[dict | None, float, int | None, str]:
        text, dt, toks = self.chat(user, schema, max_tokens)
        try:
            obj = json.loads(text)
            jsonschema.validate(obj, schema)
            return obj, dt, toks, text
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return None, dt, toks, text


def run_judge(c: Client, cases: list[dict]) -> list[Result]:
    out = []
    for k in cases:
        src_lang, tgt_lang = ("English", "French") if k["direction"] == "en_fr" else ("French", "English")
        prompt = (
            f"Evaluate a learner's translation ({k['level']} level) from {src_lang} to {tgt_lang}.\n"
            f"Source: {k['source']}\nReference translation(s): {json.dumps(k['references'], ensure_ascii=False)}\n"
            f"Learner answer: {k['answer']}\n\n"
            "The references are examples, not the only correct answers. Verdict: 'correct' if the answer "
            "is grammatical and conveys the meaning naturally (other wordings and Québec usage are fine); "
            "'acceptable' if correct but slightly unnatural; 'incorrect' if it contains any grammatical, "
            "spelling/accent or meaning error. List the error categories (empty if none), give a corrected "
            "version (or the answer itself if correct), and a short explanation."
        )
        obj, dt, toks, raw = c.structured(prompt, JUDGE_SCHEMA)
        if obj is None:
            out.append(Result(c.model, "judge", k["id"], False, 0, dt, False, toks, {"raw": raw[:400]}))
            continue
        said_ok = obj["verdict"] in ("correct", "acceptable")
        want_ok = k["expect"]["verdict"] == "correct"
        verdict_ok = said_ok == want_ok
        cat_hit = None
        if not want_ok and k["expect"].get("categories"):
            cat_hit = bool(set(obj["categories"]) & set(k["expect"]["categories"]))
        out.append(Result(c.model, "judge", k["id"], verdict_ok, 1.0 if verdict_ok else 0.0, dt, True, toks,
                          {"verdict": obj["verdict"], "categories": obj["categories"], "category_hit": cat_hit,
                           "expected": k["expect"], "corrected": obj["corrected"], "explanation": obj["explanation"]}))
    return out


def run_mcq(c: Client, cases: list[dict], task: str) -> list[Result]:
    out = []
    for k in cases:
        opts = "\n".join(f"{key}) {val}" for key, val in k["options"].items())
        obj, dt, toks, raw = c.structured(f"Choose the single correct option.\n\n{k['question']}\n{opts}", MCQ_SCHEMA, 300)
        ok = obj is not None and obj["answer"] == k["answer"]
        out.append(Result(c.model, task, k["id"], ok, float(ok), dt, obj is not None, toks,
                          {"answer": obj and obj["answer"], "expected": k["answer"]}))
    return out


def run_conj(c: Client, cases: list[dict]) -> list[Result]:
    out = []
    for k in cases:
        prompt = (f"Conjugate « {k['verb']} » in the {k['tense']}. For each person give the full form including "
                  "the subject pronoun as written in a sentence (e.g. « j'étais », « je me lève », « je suis venu »). "
                  "Use 'il' for third person singular and 'ils' for third person plural. For the subjunctive, omit « que ».")
        obj, dt, toks, raw = c.structured(prompt, CONJ_SCHEMA, 300)
        if obj is None:
            out.append(Result(c.model, "conjugation", k["id"], False, 0, dt, False, toks, {"raw": raw[:300]}))
            continue
        wrong = {}
        for p in PERSONS:
            want = k["forms"][p]
            wants = {norm(w) for w in (want if isinstance(want, list) else [want])}
            if norm(obj["forms"][p]) not in wants:
                wrong[p] = {"got": obj["forms"][p], "want": want}
        score = 1 - len(wrong) / len(PERSONS)
        out.append(Result(c.model, "conjugation", k["id"], not wrong, score, dt, True, toks, {"wrong": wrong}))
    return out


def run_genders(c: Client, spec: dict) -> list[Result]:
    nouns = list(spec["nouns"])
    obj, dt, toks, raw = c.structured(
        f"For each French noun give its grammatical gender (m/f) and indefinite article: {', '.join(nouns)}.",
        GENDER_SCHEMA, 900)
    if obj is None:
        return [Result(c.model, "genders", spec["id"], False, 0, dt, False, toks, {"raw": raw[:300]})]
    got = {norm(i["noun"]): i for i in obj["items"]}
    wrong = {}
    for n, g in spec["nouns"].items():
        item = got.get(norm(n))
        art = "un" if g == "m" else "une"
        if not item or item["gender"] != g or item["indefinite_article"] != art:
            wrong[n] = item
    score = 1 - len(wrong) / len(nouns)
    return [Result(c.model, "genders", spec["id"], not wrong, score, dt, True, toks, {"wrong": wrong})]


def run_open(c: Client, specs: list[dict]) -> list[Result]:
    out = []
    for s in specs:
        schema = FILL_SCHEMA if s["kind"] == "fill_blank" else TRANS_SCHEMA
        obj, dt, toks, raw = c.structured(s["instruction"], schema, 1200)
        if obj is None:
            out.append(Result(c.model, "open_gen", s["id"], False, 0, dt, False, toks, {"raw": raw[:400]}))
            continue
        items, problems = obj["items"], []
        if len(items) != s["count"]:
            problems.append(f"expected {s['count']} items, got {len(items)}")
        for i, it in enumerate(items):
            if s["kind"] == "fill_blank":
                if it["sentence"].count("___") != 1:
                    problems.append(f"item {i}: needs exactly one ___")
                filled = it["sentence"].replace("___", it["answer"]).lower().split()
                if any(a == b and len(a) > 2 for a, b in zip(filled, filled[1:])):
                    problems.append(f"item {i}: word repeated after filling the blank: {it['sentence']!r}")
                if not ETRE_AUX.search(it["answer"].lower()):
                    problems.append(f"item {i}: answer lacks an être auxiliary: {it['answer']!r}")
                if norm(it["infinitive"]).removeprefix("se ").removeprefix("s'") not in ETRE_VERBS and not norm(it["infinitive"]).startswith(("se ", "s'")):
                    problems.append(f"item {i}: {it['infinitive']!r} does not take être")
            else:
                answers = {norm(a) for a in it["accepted_french"]}
                if len(answers) < 2:
                    problems.append(f"item {i}: fewer than 2 distinct French answers")
        checks = 1 + len(items)
        score = max(0.0, 1 - len(problems) / checks)
        out.append(Result(c.model, "open_gen", s["id"], not problems, score, dt, True, toks,
                          {"problems": problems, "output": obj}))
    return out


def run_explain(c: Client, cases: list[dict]) -> list[Result]:
    out = []
    for k in cases:
        text, dt, toks = c.chat(k["question"] + " Answer in at most 150 words.", None, 400)
        hits = [any(re.search(p, text, re.I) for p in group) for group in k["rubric"]]
        score = sum(hits) / len(hits)
        out.append(Result(c.model, "explain", k["id"], score == 1, score, dt, None, toks, {"text": text}))
    return out


def system_memory() -> dict[str, Any]:
    swap = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True).stdout
    mp = subprocess.run(["memory_pressure"], capture_output=True, text=True).stdout
    free = re.search(r"free percentage: (\d+)%", mp)
    used = re.search(r"used = ([\d.]+)M", swap)
    return {"swap_used_mb": float(used.group(1)) if used else None, "free_pct": int(free.group(1)) if free else None}


def model_stats(base: str, model: str) -> dict[str, Any]:
    http = httpx.Client(timeout=600)
    t = time.perf_counter()
    http.post(f"{base}/api/generate", json={"model": model, "prompt": "", "keep_alive": "30m"}).raise_for_status()
    load_s = time.perf_counter() - t
    r = http.post(f"{base}/api/generate", json={
        "model": model, "stream": False, "think": False,
        "prompt": "Écris un paragraphe d'environ 150 mots sur l'hiver à Montréal.",
        "options": {"temperature": 0, "num_predict": 256},
    }).json()
    ps = next((m for m in http.get(f"{base}/api/ps").json().get("models", []) if m["name"] == model), {})
    return {
        "load_s": round(load_s, 2),
        "decode_tok_s": round(r["eval_count"] / (r["eval_duration"] / 1e9), 1),
        "prefill_tok_s": round(r["prompt_eval_count"] / max(r["prompt_eval_duration"] / 1e9, 1e-9), 1),
        "resident_gb": round(ps.get("size", 0) / 1e9, 2),
        "resident_vram_gb": round(ps.get("size_vram", 0) / 1e9, 2),
        "context_length": ps.get("context_length"),
    }


def unload(base: str, model: str) -> None:
    httpx.post(f"{base}/api/generate", json={"model": model, "prompt": "", "keep_alive": 0}, timeout=60)


def pct(values: list[float], q: float) -> float:
    return round(statistics.quantiles(values, n=10)[int(q * 10) - 1], 2) if len(values) >= 2 else round(values[0], 2)


def summarize(model: str, results: list[Result], stats: dict, mem: dict) -> dict[str, Any]:
    by: dict[str, list[Result]] = {}
    for r in results:
        by.setdefault(r.task, []).append(r)
    s: dict[str, Any] = {"model": model, **stats, **mem}
    for task, rs in by.items():
        s[f"{task}_score"] = round(sum(r.score for r in rs) / len(rs), 3)
    judge = by.get("judge", [])
    cat = [r.detail["category_hit"] for r in judge if r.detail.get("category_hit") is not None]
    s["judge_category_hit"] = round(sum(cat) / len(cat), 3) if cat else None
    qc_judge = [r for r in judge if r.case_id.startswith("qc-")]
    s["judge_quebec_accept"] = round(sum(r.ok for r in qc_judge) / len(qc_judge), 3) if qc_judge else None
    structured = [r for r in results if r.json_valid is not None]
    s["json_valid_rate"] = round(sum(bool(r.json_valid) for r in structured) / len(structured), 3)
    if judge:
        lat = [r.latency_s for r in judge]
        s["judge_latency_p50"], s["judge_latency_p90"] = pct(lat, 0.5), pct(lat, 0.9)
    return s


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="+")
    ap.add_argument("--base", default="http://127.0.0.1:11435")
    ap.add_argument("--provider", choices=["ollama", "anthropic"], default="ollama")
    ap.add_argument("--out", type=Path, default=HERE / "results" / datetime.now().strftime("%Y%m%d-%H%M"))
    ap.add_argument("--tasks", default="judge,grammar,quebec,conjugation,genders,open_gen,explain")
    ap.add_argument("--judge-version", type=int, choices=[1, 2], default=2)
    ap.add_argument("--no-lexicon", action="store_true", help="judge v2 without Québec grounding")
    args = ap.parse_args()
    tasks = set(args.tasks.split(","))
    lexicon = None if args.no_lexicon else yaml.safe_load((CASES / "quebec_lexicon_seed.yaml").read_text())
    args.out.mkdir(parents=True, exist_ok=True)

    judge = yaml.safe_load((CASES / "judge.yaml").read_text())
    grammar = yaml.safe_load((CASES / "grammar.yaml").read_text())
    quebec = yaml.safe_load((CASES / "quebec.yaml").read_text())
    gen = yaml.safe_load((CASES / "generation.yaml").read_text())
    explain = yaml.safe_load((CASES / "explain.yaml").read_text())

    summaries = []
    for model in args.models:
        print(f"\n=== {model}", flush=True)
        mem_before = system_memory()
        c: Any
        if args.provider == "anthropic":
            stats: dict[str, Any] = {}
            c = AnthropicClient(model)
        else:
            stats = model_stats(args.base, model)
            print(f"  load {stats['load_s']}s, decode {stats['decode_tok_s']} tok/s, resident {stats['resident_gb']} GB", flush=True)
            c = Client(args.base, model)
        results: list[Result] = []
        for name, fn in [
            ("judge", lambda: run_judge_v2(c, judge, lexicon) if args.judge_version == 2 else run_judge(c, judge)),
            ("grammar", lambda: run_mcq(c, grammar, "grammar")),
            ("quebec", lambda: run_mcq(c, quebec, "quebec")),
            ("conjugation", lambda: run_conj(c, gen["conjugation"])),
            ("genders", lambda: run_genders(c, gen["genders"])),
            ("open_gen", lambda: run_open(c, gen["open"])),
            ("explain", lambda: run_explain(c, explain)),
        ]:
            if name not in tasks:
                continue
            t = time.perf_counter()
            rs = fn()
            results += rs
            print(f"  {name:12s} {sum(r.score for r in rs) / len(rs):.2f}  ({time.perf_counter() - t:.0f}s)", flush=True)
        mem_after = system_memory()
        mem = {"swap_before_mb": mem_before["swap_used_mb"], "swap_after_mb": mem_after["swap_used_mb"],
               "free_pct_after": mem_after["free_pct"]}
        if args.provider == "anthropic":
            stats.update(input_tokens=c.input_tokens, output_tokens=c.output_tokens, cost_usd=round(c.cost_usd, 4))
            print(f"  tokens in {c.input_tokens}, out {c.output_tokens}, cost ${c.cost_usd:.4f}", flush=True)
        else:
            unload(args.base, model)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", model)
        with (args.out / f"{safe}.jsonl").open("w") as f:
            for r in results:
                f.write(json.dumps(asdict(r), ensure_ascii=False) + "\n")
        summaries.append(summarize(model, results, stats, mem))

    (args.out / "summary.json").write_text(json.dumps(summaries, indent=2, ensure_ascii=False))
    cols = ["model", "judge_score", "judge_category_hit", "judge_quebec_accept", "grammar_score", "quebec_score",
            "conjugation_score", "genders_score", "open_gen_score", "explain_score", "json_valid_rate",
            "judge_latency_p50", "judge_latency_p90", "decode_tok_s", "prefill_tok_s", "load_s", "resident_gb",
            "swap_before_mb", "swap_after_mb", "free_pct_after", "input_tokens", "output_tokens", "cost_usd"]
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    lines += ["| " + " | ".join(str(s.get(k, "")) for k in cols) + " |" for s in summaries]
    (args.out / "scorecard.md").write_text("# Bake-off scorecard\n\n" + "\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    print(f"\nResults: {args.out}")


if __name__ == "__main__":
    main()
