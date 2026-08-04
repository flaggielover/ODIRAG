"""Retrieval fusion and orchestration."""

from typing import TYPE_CHECKING, Any

from app.retrieval.analysis import RetrievalQueryAnalysis, RetrievalQueryAnalyzer
from app.retrieval.models import RetrievalHit
from app.retrieval.rrf import reciprocal_rank_fusion

if TYPE_CHECKING:
    from app.retrieval.engine import (
        RetrievalConfig,
        RetrievalEngine,
        RetrievalMode,
        RetrievalTrace,
    )

__all__ = [
    "RetrievalConfig",
    "RetrievalEngine",
    "RetrievalHit",
    "RetrievalMode",
    "RetrievalQueryAnalysis",
    "RetrievalQueryAnalyzer",
    "RetrievalTrace",
    "reciprocal_rank_fusion",
]


def __getattr__(name: str) -> Any:
    if name in {"RetrievalConfig", "RetrievalEngine", "RetrievalMode", "RetrievalTrace"}:
        from app.retrieval import engine

        return getattr(engine, name)
    raise AttributeError(name)
