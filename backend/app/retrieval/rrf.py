from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from app.retrieval.models import RetrievalHit


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[RetrievalHit]], *, rrf_k: int = 60, limit: int | None = None
) -> list[RetrievalHit]:
    if rrf_k <= 0:
        raise ValueError("rrf_k must be positive")
    scores: dict[str, float] = defaultdict(float)
    exemplars: dict[str, RetrievalHit] = {}
    origins: dict[str, set[str]] = defaultdict(set)
    for ranking in rankings:
        seen: set[str] = set()
        for rank, hit in enumerate(ranking, start=1):
            if hit.chunk_id in seen:
                continue
            seen.add(hit.chunk_id)
            scores[hit.chunk_id] += 1.0 / (rrf_k + rank)
            exemplars.setdefault(hit.chunk_id, hit)
            origins[hit.chunk_id].add(hit.source)
    ordered = sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))
    if limit is not None:
        ordered = ordered[: max(0, limit)]
    return [
        exemplars[chunk_id].with_score(scores[chunk_id], rank, "+".join(sorted(origins[chunk_id])))
        for rank, chunk_id in enumerate(ordered, start=1)
    ]
