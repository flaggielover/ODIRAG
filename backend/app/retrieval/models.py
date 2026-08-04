from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: str
    document_id: str
    content: str
    title: str
    source_url: str
    score: float
    rank: int = 0
    source: str = "unknown"
    metadata: dict[str, Any] = field(default_factory=dict)

    def with_score(self, score: float, rank: int, source: str) -> RetrievalHit:
        return replace(self, score=score, rank=rank, source=source)
