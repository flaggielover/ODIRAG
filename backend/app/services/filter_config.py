from __future__ import annotations

from pathlib import Path

import yaml

from app.filters import RuleFilterConfig


def load_filter_config(path: Path) -> RuleFilterConfig:
    return RuleFilterConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
