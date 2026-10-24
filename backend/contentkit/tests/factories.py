"""Builders for minimal valid content used across contentkit and importer tests."""

from pathlib import Path
from typing import Any

from contentkit.yamlio import dump_yaml


def lesson_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "a2-passe-compose-er",
        "content_version": 1,
        "level": "A2",
        "unit": "a2-u01-past",
        "title": "Le passé composé des verbes en -er",
        "title_en": "The passé composé of -er verbs",
        "objectives": ["Form the passé composé with avoir"],
        "grammar_topics": ["passe-compose-avoir"],
        "estimated_minutes": 20,
        "sections": [
            {
                "type": "explanation",
                "id": "intro",
                "heading": "How it works",
                "body": "Use **avoir** + participle.\nFor example: j'ai mangé.",
            },
            {
                "type": "reading",
                "id": "story",
                "title": "Ma fin de semaine",
                "passage_fr": "Samedi, j'ai magasiné avec ma blonde. Nous avons soupé au resto.",
                "translation_en": (
                    "On Saturday I went shopping with my girlfriend. We had supper at a restaurant."
                ),
            },
        ],
        "exercises": [
            {
                "type": "fill_blank",
                "id": "ex-01",
                "sentence": "Hier, j'___ une poutine.",
                "answers": ["ai mangé"],
                "hint": "(manger)",
                "translation_en": "Yesterday I ate a poutine.",
            },
            {
                "type": "translate",
                "id": "ex-02",
                "direction": "en_fr",
                "prompt": "We went shopping.",
                "accepted_answers": ["On a magasiné.", "Nous avons magasiné."],
            },
            {
                "type": "comprehension",
                "id": "ex-03",
                "reading_id": "story",
                "question": "Qu'est-ce qu'ils ont fait samedi ?",
                "options": ["Ils ont magasiné", "Ils ont dormi"],
                "answer_index": 0,
                "explanation": "« j'ai magasiné »",
            },
        ],
    }
    data.update(overrides)
    return data


CURRICULUM = {
    "level": "A2",
    "title": "Élémentaire",
    "summary": "Past tenses.",
    "units": [
        {
            "id": "a2-u01-past",
            "title": "Raconter au passé",
            "objectives": ["Tell stories"],
            "lessons": [
                {
                    "id": "a2-passe-compose-er",
                    "title": "PC -er",
                    "kind": "grammar",
                    "objectives": ["x"],
                    "grammar_topics": ["passe-compose-avoir"],
                },
                {
                    "id": "a2-imparfait",
                    "title": "Imparfait",
                    "kind": "grammar",
                    "objectives": ["x"],
                    "grammar_topics": ["imparfait"],
                    "prerequisites": ["a2-passe-compose-er"],
                },
            ],
        }
    ],
}
TOPICS = {
    "topics": [
        {"id": "passe-compose-avoir", "level": "A2", "title": "PC"},
        {"id": "imparfait", "level": "A2", "title": "Imparfait"},
    ]
}


def make_repo(root: Path, lessons: list[dict[str, Any]] | None = None) -> Path:
    (root / "curriculum").mkdir(parents=True)
    (root / "grammar").mkdir()
    (root / "curriculum" / "a2.yaml").write_text(dump_yaml(CURRICULUM))
    (root / "grammar" / "topics.yaml").write_text(dump_yaml(TOPICS))
    for lesson in lessons if lessons is not None else [lesson_data()]:
        write_lesson(root, lesson)
    return root


def write_lesson(root: Path, lesson: dict[str, Any]) -> Path:
    path = root / "lessons" / lesson["level"].lower() / f"{lesson['id']}.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(lesson))
    return path
