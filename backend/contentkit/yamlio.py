"""Canonical YAML IO and content hashing.

The content hash covers what a learner sees: it excludes `content_version` and `provenance`,
so "same id + same version + different hash" means the content changed without a version bump.
"""

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

HASH_EXCLUDE = {"content_version", "provenance"}


class _Dumper(yaml.SafeDumper):
    pass


def _str_representer(dumper: yaml.SafeDumper, value: str) -> yaml.ScalarNode:
    # Multi-line prose as block scalars: readable, diffable reviews.
    style = "|" if "\n" in value else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)


_Dumper.add_representer(str, _str_representer)


def dump_yaml(data: dict[str, Any]) -> str:
    return yaml.dump(data, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=100)


def load_yaml(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def to_data(model: BaseModel) -> dict[str, Any]:
    """Plain data for serialization: no None/default noise, stable field order."""
    return model.model_dump(mode="json", exclude_none=True)


def content_hash(model: BaseModel) -> str:
    data = model.model_dump(mode="json", exclude=HASH_EXCLUDE)
    canonical = json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
