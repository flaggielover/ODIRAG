from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from time import perf_counter
from typing import Any

from app.bm25 import BM25Index
from app.embedding import EmbeddingProvider
from app.providers import ProviderResponseError
from app.rerank import RerankProvider, RerankResult
from app.retrieval.analysis import RetrievalQueryAnalysis, RetrievalQueryAnalyzer
from app.retrieval.models import RetrievalHit
from app.retrieval.rrf import reciprocal_rank_fusion
from app.vector_store import VectorStore


class RetrievalMode(StrEnum):
    BM25 = "bm25"
    VECTOR = "vector"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    rerank_top_k: int = 8
    final_top_k: int = 5
    score_threshold: float = 0.0

    def __post_init__(self) -> None:
        values = (
            self.bm25_top_k,
            self.vector_top_k,
            self.rrf_k,
            self.rerank_top_k,
            self.final_top_k,
        )
        if any(value <= 0 for value in values):
            raise ValueError("retrieval limits and rrf_k must be positive")
        if self.score_threshold < 0:
            raise ValueError("score_threshold must be non-negative")


@dataclass(frozen=True, slots=True)
class RetrievalTrace:
    trace_id: str
    mode: RetrievalMode
    query: str
    filters: dict[str, Any]
    analysis: RetrievalQueryAnalysis
    config: RetrievalConfig
    bm25_results: tuple[RetrievalHit, ...]
    vector_results: tuple[RetrievalHit, ...]
    fusion_results: tuple[RetrievalHit, ...]
    rerank_results: tuple[RetrievalHit, ...]
    final_results: tuple[RetrievalHit, ...]
    timings_ms: dict[str, float]
    warnings: tuple[str, ...]


class RetrievalEngine:
    def __init__(
        self,
        *,
        bm25_index: BM25Index,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        rerank_provider: RerankProvider,
        config: RetrievalConfig | None = None,
        analyzer: RetrievalQueryAnalyzer | None = None,
    ) -> None:
        self.bm25_index = bm25_index
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.rerank_provider = rerank_provider
        self.config = config or RetrievalConfig()
        self.analyzer = analyzer or RetrievalQueryAnalyzer()

    async def search(
        self,
        query: str,
        *,
        mode: RetrievalMode = RetrievalMode.HYBRID_RERANK,
        filters: dict[str, Any] | None = None,
    ) -> RetrievalTrace:
        started = perf_counter()
        timings: dict[str, float] = {}
        warnings: list[str] = []
        stage_started = perf_counter()
        analysis = self.analyzer.analyze(query, filters)
        timings["analysis"] = _elapsed_ms(stage_started)
        parsed_filters = analysis.applied_filters
        bm25_hits: list[RetrievalHit] = []
        vector_hits: list[RetrievalHit] = []
        if mode in {RetrievalMode.BM25, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK}:
            stage_started = perf_counter()
            bm25_hits = self.bm25_index.search(
                analysis.normalized_query, self.config.bm25_top_k, parsed_filters
            )
            timings["bm25"] = _elapsed_ms(stage_started)
        if mode in {RetrievalMode.VECTOR, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK}:
            stage_started = perf_counter()
            query_vector = await self.embedding_provider.embed_query(analysis.normalized_query)
            timings["embedding"] = _elapsed_ms(stage_started)
            stage_started = perf_counter()
            vector_hits = await self.vector_store.search(
                query_vector, self.config.vector_top_k, parsed_filters
            )
            timings["vector"] = _elapsed_ms(stage_started)
        stage_started = perf_counter()
        if mode is RetrievalMode.BM25:
            fused = bm25_hits
        elif mode is RetrievalMode.VECTOR:
            fused = vector_hits
        else:
            fused = reciprocal_rank_fusion(
                [bm25_hits, vector_hits],
                rrf_k=self.config.rrf_k,
                limit=max(self.config.rerank_top_k, self.config.final_top_k),
            )
        timings["fusion"] = _elapsed_ms(stage_started)
        reranked: list[RetrievalHit] = []
        candidates = fused
        if mode is RetrievalMode.HYBRID_RERANK and fused:
            if self.rerank_provider.model_name == "disabled":
                warnings.append("rerank_provider_disabled")
            else:
                stage_started = perf_counter()
                ordering = await self.rerank_provider.rerank(
                    analysis.normalized_query,
                    [hit.content for hit in fused],
                    self.config.rerank_top_k,
                )
                reranked = self._validated_rerank(fused, ordering)
                timings["rerank"] = _elapsed_ms(stage_started)
                candidates = reranked
        final = [hit for hit in candidates if hit.score >= self.config.score_threshold][
            : self.config.final_top_k
        ]
        timings["total"] = _elapsed_ms(started)
        return RetrievalTrace(
            str(uuid.uuid4()),
            mode,
            analysis.normalized_query,
            parsed_filters,
            analysis,
            self.config,
            tuple(bm25_hits),
            tuple(vector_hits),
            tuple(fused),
            tuple(reranked),
            tuple(final),
            timings,
            tuple(warnings),
        )

    @staticmethod
    def _validated_rerank(
        fused: list[RetrievalHit], ordering: list[RerankResult]
    ) -> list[RetrievalHit]:
        reranked: list[RetrievalHit] = []
        seen: set[int] = set()
        for rank, item in enumerate(ordering, start=1):
            if item.index in seen or not 0 <= item.index < len(fused):
                raise ProviderResponseError("rerank", "result indices are invalid or duplicated")
            if not 0 <= item.score <= 1:
                raise ProviderResponseError("rerank", "scores must be between zero and one")
            seen.add(item.index)
            reranked.append(fused[item.index].with_score(item.score, rank, "rerank"))
        return reranked


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)
