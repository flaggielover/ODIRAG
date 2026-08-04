from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.source import SourceCreate


class SourceConfigFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    sources: list[SourceCreate]


def load_source_config(path: Path) -> SourceConfigFile:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return SourceConfigFile.model_validate(payload)
