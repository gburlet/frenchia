"""Measure the production translation grader on the curated judge cases:
docker compose exec -T backend python manage.py grader_eval < evals/french/judge.yaml"""

import statistics
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from contentkit.reference import Reference
from exercises.grading import PROMPT_VERSION, grade_translate
from inference.providers import get_chat_model


class Command(BaseCommand):
    help = (
        "Run the translation grader on judge cases (YAML on stdin) and report accuracy and latency."
    )

    def handle(self, *args: Any, **options: Any) -> None:
        cases = yaml.safe_load(sys.stdin)
        chat, ref = get_chat_model(), Reference.load(Path(settings.CONTENT_DIR))
        correct = category_hits = category_total = 0
        latencies: list[float] = []
        for case in cases:
            payload = {
                "direction": case["direction"],
                "prompt": case["source"],
                "accepted_answers": case["references"],
            }
            started = time.perf_counter()
            grade = grade_translate(
                payload, case["answer"], level=case["level"], chat=chat, ref=ref
            )
            elapsed = time.perf_counter() - started
            if grade.grading == "llm":
                latencies.append(elapsed)
            want_ok = case["expect"]["verdict"] == "correct"
            ok = (grade.verdict != "incorrect") == want_ok and grade.status == "graded"
            correct += ok
            if not want_ok and case["expect"].get("categories"):
                category_total += 1
                found = {
                    e["category"] for e in grade.feedback["errors"] if e["severity"] == "error"
                }
                category_hits += bool(found & set(case["expect"]["categories"]))
            mark = "✓" if ok else "✗"
            self.stdout.write(
                f"{mark} {case['id']:10s} {grade.verdict or grade.status:10s} {elapsed:5.1f}s"
                f"  {grade.feedback.get('summary', '')[:70]}"
            )
        p50 = statistics.median(latencies) if latencies else 0
        p90 = statistics.quantiles(latencies, n=10)[8] if len(latencies) > 1 else p50
        self.stdout.write(
            f"\n{PROMPT_VERSION} on {chat.model}: verdicts {correct}/{len(cases)} "
            f"({correct / len(cases):.2f}), categories {category_hits}/{category_total}, "
            f"LLM latency p50 {p50:.1f}s p90 {p90:.1f}s over {len(latencies)} calls"
        )
