"""A scripted ChatModel that answers each generation step with valid content."""

import json
from collections.abc import Sequence
from typing import Any

from inference.llm import Completion, Message

READING = "Samedi passé, j'ai magasiné au centre-ville. Ensuite, nous avons soupé chez ma sœur."

STEP_OUTPUTS: dict[str, Any] = {
    "ExplanationStep": {
        "title_en": "The passé composé of -er verbs",
        "heading": "Le passé composé",
        "body": "Use **avoir** + past participle.\nExample: **j'ai mangé**.",
    },
    "TableStep": {
        "include": True,
        "heading": "Avoir au présent",
        "columns": ["Pronom", "Avoir"],
        "rows": [["j'", "ai"], ["tu", "as"]],
        "caption": "Auxiliary",
    },
    "ExamplesStep": {
        "heading": "Exemples",
        "examples": [
            {
                "fr": f"J'ai parlé avec Marie {i}.",
                "en": f"I spoke with Marie {i}.",
                "region": "common",
            }
            for i in range(6)
        ],
    },
    "VocabularyStep": {
        "heading": "Mots",
        "items": [
            {
                "fr": f"mot{i}",
                "en": f"word{i}",
                "pos": "other",
                "region": "common",
                "formality": "standard",
            }
            for i in range(10)
        ],
    },
    "RegionalNoteStep": {
        "heading": "Au Québec",
        "body": "The passé composé is used the same way.",
        "variants": [],
    },
    "ReadingStep": {
        "title": "Ma fin de semaine",
        "passage_fr": READING,
        "translation_en": "Last Saturday I went shopping downtown.",
        "glossary": [
            {"fr": "ensuite", "en": "then", "pos": "adverb"},
            {"fr": "chez", "en": "at the home of", "pos": "other"},
            {"fr": "passé", "en": "last", "pos": "adjective"},
        ],
    },
}


def fill_batch(n: int, bad: bool) -> dict[str, Any]:
    first = {
        "sentence": "Hier, elle ___ au dépanneur.",
        "answers": ["a allé" if bad else "est allée"],
        "hint": "(aller)",
        "translation_en": "Yesterday she went to the store.",
    }
    rest = [
        {
            "sentence": f"Hier, j'___ un café {i}.",
            "answers": ["ai mangé"],
            "hint": "(manger)",
            "translation_en": "I ate.",
        }
        for i in range(n - 1)
    ]
    return {"items": [first, *rest]}


def choice_batch(n: int) -> dict[str, Any]:
    return {
        "items": [
            {
                "question": f"Question {i} ?",
                "options": ["a", "b", "c"],
                "answer_index": 1,
                "explanation": "Because.",
            }
            for i in range(n)
        ]
    }


def translate_batch(n: int) -> dict[str, Any]:
    return {
        "items": [
            {
                "prompt": f"I ate {i}.",
                "accepted_answers": [f"J'ai mangé {i}.", f"Moi, j'ai mangé {i}."],
                "hint": "manger",
            }
            for i in range(n)
        ]
    }


class ScriptedChat:
    model = "scripted"

    def __init__(self, *, bad_fill_first: bool = False) -> None:
        self.bad_fill_first = bad_fill_first
        self.calls: list[tuple[str, list[Message]]] = []

    def complete(
        self,
        messages: Sequence[Message],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> Completion:
        title = (json_schema or {}).get("title", "")
        self.calls.append((title, list(messages)))
        if title == "Critique":
            sentence = messages[-1].content.split("Sentence: ", 1)[1].split("\n", 1)[0]
            errors = [{"severity": "error", "span": "a parlé son ami", "explanation": "parler à"}]
            data = {"errors": errors if "parlé son ami" in sentence else []}
        elif title in STEP_OUTPUTS:
            data = STEP_OUTPUTS[title]
        elif title.startswith("FillBlankDraftBatch"):
            first_attempt = not any(t == title for t, _ in self.calls[:-1])
            data = fill_batch(
                int(title.removeprefix("FillBlankDraftBatch")),
                self.bad_fill_first and first_attempt,
            )
        elif title.startswith("TranslateDraftBatch"):
            data = translate_batch(int(title.removeprefix("TranslateDraftBatch")))
        elif title.startswith("ChoiceDraftBatch"):
            data = choice_batch(int(title.removeprefix("ChoiceDraftBatch")))
        else:  # revision of an existing item: echo it back with a marker in a text field
            current = json.loads(messages[-1].content.split("Current content (JSON):\n", 1)[1])
            current["id"] = "renamed-by-llm"
            if "heading" in current:
                current["heading"] += " (révisé)"
            data = current
        return Completion(
            content=json.dumps(data, ensure_ascii=False),
            model=self.model,
            latency_ms=1,
            completion_tokens=10,
        )

    def health(self) -> bool:
        return True
