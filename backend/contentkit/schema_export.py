"""Export JSON Schema for content files (editor validation; see content/schemas/)."""

import json
from pathlib import Path

from pydantic import BaseModel

from .models import CurriculumLevel, GrammarTopicRegistry, Lesson

SCHEMAS: dict[str, type[BaseModel]] = {
    "curriculum-level.schema.json": CurriculumLevel,
    "grammar-topics.schema.json": GrammarTopicRegistry,
    "lesson.schema.json": Lesson,
}


def export_schemas(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, model in SCHEMAS.items():
        path = out_dir / name
        path.write_text(json.dumps(model.model_json_schema(), indent=2, ensure_ascii=False) + "\n")
        written.append(path)
    return written
