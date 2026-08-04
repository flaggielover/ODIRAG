from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.chunking.heading import ChunkingConfig


def load_chunking_config(path: Path) -> ChunkingConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("chunking configuration must be a mapping")
    section: Any = payload.get("chunking", payload)
    if not isinstance(section, dict):
        raise ValueError("chunking section must be a mapping")
    allowed = {"target_chars", "min_chars", "max_chars", "overlap_chars"}
    unknown = set(section) - allowed
    if unknown:
        raise ValueError(f"unsupported chunking settings: {sorted(unknown)}")
    return ChunkingConfig(**section)
