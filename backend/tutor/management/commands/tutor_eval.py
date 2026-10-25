"""Run curated tutor scenarios through the production prompt and grounding:
docker compose exec -T backend python manage.py tutor_eval < evals/french/tutor.yaml"""

import asyncio
import re
import sys
import time
from pathlib import Path
from typing import Any

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand

from contentkit.reference import Reference
from inference.llm import Message
from inference.providers import get_chat_model
from tutor.context import _describe_exercise, _hint_verb
from tutor.prompts import PROMPT_VERSION, SYSTEM


def scenario_context(case: dict[str, Any], ref: Reference) -> str:
    """The same blocks build_context produces, from a scenario instead of the database."""
    exercise = case["exercise"]
    description = _describe_exercise(exercise)
    parts = [
        "Learner: CEFR A2, aiming for B2; learning Québec French.",
        "Current exercise:\n" + description,
    ]
    if answer := case.get("answer"):
        parts.append(f"The learner answered: «{answer}».")
    else:
        parts.append("The learner has NOT answered this exercise yet: give hints, not the answer.")
    hint = _hint_verb(exercise)
    verbs = ([hint] if hint else []) + ref.verbs_in(
        case.get("answer", ""), description, case["question"]
    )
    facts = [f for f in dict.fromkeys(ref.verb_facts(v) for v in verbs) if f][:4]
    if facts:
        parts.append(
            "Verified verb facts (from the conjugation reference; authoritative):\n"
            + "\n".join(f"- {f}" for f in facts)
        )
    terms = ref.quebec_terms_in(description, case.get("answer", ""), case["question"])
    if terms:
        parts.append(
            "Verified Québec usage (authoritative):\n"
            + "\n".join(
                f"- {t.term}: {t.meaning} (France: {t.france}; {t.formality})" for t in terms
            )
        )
    return "\n\n".join(parts)


class Command(BaseCommand):
    help = "Score the tutor on curated scenarios (YAML on stdin)."

    def handle(self, *args: Any, **options: Any) -> None:
        cases = yaml.safe_load(sys.stdin)
        ref = Reference.load(Path(settings.CONTENT_DIR))
        chat = get_chat_model()
        passed = 0
        first_tokens: list[float] = []

        async def ask(messages: list[Message]) -> tuple[str, float]:
            started, first, parts = time.perf_counter(), 0.0, []
            async for delta in chat.stream(messages, temperature=0.3, max_tokens=700):
                first = first or time.perf_counter() - started
                parts.append(delta)
            return "".join(parts), first

        for case in cases:
            messages = [
                Message("system", SYSTEM.format(context=scenario_context(case, ref))),
                Message("user", case["question"]),
            ]
            reply, first = asyncio.run(ask(messages))
            first_tokens.append(first)
            missing = [g for g in case["must"] if not any(re.search(p, reply, re.I) for p in g)]
            forbidden = [p for p in case.get("must_not", []) if re.search(p, reply, re.I)]
            ok = not missing and not forbidden
            passed += ok
            self.stdout.write(
                f"\n{'✓' if ok else '✗'} {case['id']} (first token {first:.1f}s)"
                + (f"  missing {missing}" if missing else "")
                + (f"  FORBIDDEN {forbidden}" if forbidden else "")
            )
            self.stdout.write("    " + " ".join(reply.split())[:500])
        first_tokens.sort()
        self.stdout.write(
            f"\n{PROMPT_VERSION} on {chat.model}: {passed}/{len(cases)} scenarios pass; "
            f"first token median {first_tokens[len(first_tokens) // 2]:.1f}s"
        )
