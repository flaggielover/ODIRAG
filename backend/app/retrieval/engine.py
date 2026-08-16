from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
from time import perf_counter
from typing import Any

from app.bm25 import BM25Index
from app.embedding import EmbeddingProvider
from app.metrics import MetricsRecorder, classify_error, provider_label
from app.providers import ProviderResponseError, ProviderUnavailableError
from app.rerank import RerankProvider, RerankResponse, RerankResult
from app.retrieval.analysis import RetrievalQueryAnalysis, RetrievalQueryAnalyzer
from app.retrieval.models import RetrievalHit
from app.retrieval.rrf import reciprocal_rank_fusion
from app.vector_store import VectorStore


class RetrievalMode(StrEnum):
    BM25 = "bm25"
    VECTOR = "vector"
    HYBRID = "hybrid"
    HYBRID_RERANK = "hybrid_rerank"


class RerankFailurePolicy(StrEnum):
    OPEN = "open"
    CLOSED = "closed"


@dataclass(frozen=True, slots=True)
class RetrievalConfig:
    bm25_top_k: int = 20
    vector_top_k: int = 20
    rrf_k: int = 60
    rerank_top_k: int = 8
    final_top_k: int = 5
    score_threshold: float = 0.0
    rerank_failure_policy: RerankFailurePolicy = RerankFailurePolicy.OPEN

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
        try:
            policy = RerankFailurePolicy(self.rerank_failure_policy)
        except ValueError as exc:
            raise ValueError("rerank_failure_policy must be open or closed") from exc
        object.__setattr__(self, "rerank_failure_policy", policy)


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
    rerank_metadata: dict[str, Any]
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
        recorder: MetricsRecorder | None = None,
    ) -> None:
        self.bm25_index = bm25_index
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store
        self.rerank_provider = rerank_provider
        self.config = config or RetrievalConfig()
        self.analyzer = analyzer or RetrievalQueryAnalyzer()
        self.recorder = recorder

    async def search(
        self,
        query: str,
        *,
        mode: RetrievalMode = RetrievalMode.HYBRID_RERANK,
        filters: dict[str, Any] | None = None,
        top_k: int | None = None,
    ) -> RetrievalTrace:
        if top_k is not None and not 1 <= top_k <= 200:
            raise ValueError("top_k must be between 1 and 200")
        final_top_k = top_k or self.config.final_top_k
        bm25_top_k = max(self.config.bm25_top_k, final_top_k)
        vector_top_k = max(self.config.vector_top_k, final_top_k)
        rerank_top_k = max(self.config.rerank_top_k, final_top_k)
        effective_config = self.config
        if top_k is not None:
            effective_config = RetrievalConfig(
                bm25_top_k=bm25_top_k,
                vector_top_k=vector_top_k,
                rrf_k=self.config.rrf_k,
                rerank_top_k=rerank_top_k,
                final_top_k=final_top_k,
                score_threshold=self.config.score_threshold,
                rerank_failure_policy=self.config.rerank_failure_policy,
            )
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
            try:
                bm25_hits = self.bm25_index.search(
                    analysis.normalized_query, bm25_top_k, parsed_filters
                )
            except Exception as exc:
                duration = _elapsed_seconds(stage_started)
                timings["bm25"] = round(duration * 1000, 3)
                self._record_stage("bm25", "error", duration, exc)
                raise
            duration = _elapsed_seconds(stage_started)
            timings["bm25"] = round(duration * 1000, 3)
            self._record_stage("bm25", "success", duration)
        if mode in {RetrievalMode.VECTOR, RetrievalMode.HYBRID, RetrievalMode.HYBRID_RERANK}:
            stage_started = perf_counter()
            try:
                query_vector = await self.embedding_provider.embed_query(analysis.normalized_query)
            except Exception as exc:
                duration = _elapsed_seconds(stage_started)
                timings["embedding"] = round(duration * 1000, 3)
                self._record_provider(
                    self.embedding_provider,
                    "embed_query",
                    "error",
                    duration,
                    exc,
                )
                self._record_stage("embedding", "error", duration, exc)
                raise
            duration = _elapsed_seconds(stage_started)
            timings["embedding"] = round(duration * 1000, 3)
            self._record_provider(
                self.embedding_provider,
                "embed_query",
                "success",
                duration,
            )
            self._record_stage("embedding", "success", duration)
            stage_started = perf_counter()
            try:
                vector_hits = await self.vector_store.search(
                    query_vector, vector_top_k, parsed_filters
                )
            except Exception as exc:
                duration = _elapsed_seconds(stage_started)
                timings["vector"] = round(duration * 1000, 3)
                self._record_provider(
                    self.vector_store,
                    "vector_search",
                    "error",
                    duration,
                    exc,
                )
                self._record_stage("vector_retrieval", "error", duration, exc)
                raise
            duration = _elapsed_seconds(stage_started)
            timings["vector"] = round(duration * 1000, 3)
            self._record_provider(
                self.vector_store,
                "vector_search",
                "success",
                duration,
            )
            self._record_stage("vector_retrieval", "success", duration)
        stage_started = perf_counter()
        try:
            if mode is RetrievalMode.BM25:
                fused = bm25_hits
            elif mode is RetrievalMode.VECTOR:
                fused = vector_hits
            else:
                fused = reciprocal_rank_fusion(
                    [bm25_hits, vector_hits],
                    rrf_k=self.config.rrf_k,
                    limit=max(rerank_top_k, final_top_k),
                )
        except Exception as exc:
            duration = _elapsed_seconds(stage_started)
            timings["fusion"] = round(duration * 1000, 3)
            if mode not in {RetrievalMode.BM25, RetrievalMode.VECTOR}:
                self._record_stage("hybrid", "error", duration, exc)
            raise
        duration = _elapsed_seconds(stage_started)
        timings["fusion"] = round(duration * 1000, 3)
        if mode not in {RetrievalMode.BM25, RetrievalMode.VECTOR}:
            self._record_stage("hybrid", "success", duration)
        reranked: list[RetrievalHit] = []
        candidates = fused
        provider_name = getattr(
            self.rerank_provider,
            "provider_name",
            _class_name(self.rerank_provider),
        )
        model_name = getattr(self.rerank_provider, "model_name", "unknown")
        rerank_metadata: dict[str, Any] = {
            "applied": False,
            "provider": provider_name,
            "model": model_name,
            "failure_policy": self.config.rerank_failure_policy.value,
            "error": None,
            "error_code": None,
            "candidate_count": len(fused),
            "reranked_count": 0,
            "latency_ms": 0.0,
            "usage": {},
            "cost": None,
            "cost_measurement": "not_applicable",
        }
        if mode is RetrievalMode.HYBRID_RERANK and fused:
            if self.rerank_provider.model_name == "disabled":
                warnings.append("rerank_provider_disabled")
                self._record_stage("rerank", "skipped", 0.0)
            else:
                stage_started = perf_counter()
                try:
                    provider_output = await self.rerank_provider.rerank(
                        analysis.normalized_query,
                        [hit.content for hit in fused],
                        rerank_top_k,
                    )
                    if isinstance(provider_output, RerankResponse):
                        ordering = list(provider_output.results)
                        usage = dict(provider_output.usage)
                        cost = provider_output.cost
                        cost_measurement = provider_output.cost_measurement
                    else:
                        ordering = provider_output
                        usage = {}
                        cost = None
                        cost_measurement = (
                            "not_applicable"
                            if provider_name in {"deterministic", "none"}
                            else "not_available"
                        )
                    reranked = self._validated_rerank(fused, ordering)
                    latency_ms = _elapsed_ms(stage_started)
                    timings["rerank"] = latency_ms
                    candidates = reranked
                    rerank_metadata.update(
                        {
                            "applied": True,
                            "reranked_count": len(reranked),
                            "latency_ms": latency_ms,
                            "usage": usage,
                            "cost": cost,
                            "cost_measurement": cost_measurement,
                        }
                    )
                    self._record_provider(
                        self.rerank_provider,
                        "rerank",
                        "success",
                        latency_ms / 1000,
                    )
                    self._record_stage("rerank", "success", latency_ms / 1000)
                except Exception as exc:
                    latency_ms = _elapsed_ms(stage_started)
                    timings["rerank"] = latency_ms
                    self._record_provider(
                        self.rerank_provider,
                        "rerank",
                        "error",
                        latency_ms / 1000,
                        exc,
                    )
                    self._record_stage("rerank", "error", latency_ms / 1000, exc)
                    error_code = _rerank_error_code(exc)
                    rerank_metadata.update(
                        {
                            "error": error_code,
                            "error_code": error_code,
                            "latency_ms": latency_ms,
                            "cost_measurement": (
                                "not_applicable"
                                if provider_name in {"deterministic", "none"}
                                else "not_available"
                            ),
                        }
                    )
                    if self.config.rerank_failure_policy is RerankFailurePolicy.CLOSED:
                        raise
                    warnings.append(f"rerank_failed_open:{error_code}")
        final = [hit for hit in candidates if hit.score >= self.config.score_threshold][
            :final_top_k
        ]
        timings["total"] = _elapsed_ms(started)
        return RetrievalTrace(
            trace_id=str(uuid.uuid4()),
            mode=mode,
            query=analysis.normalized_query,
            filters=parsed_filters,
            analysis=analysis,
            config=effective_config,
            bm25_results=tuple(bm25_hits),
            vector_results=tuple(vector_hits),
            fusion_results=tuple(fused),
            rerank_results=tuple(reranked),
            final_results=tuple(final),
            rerank_metadata=rerank_metadata,
            timings_ms=timings,
            warnings=tuple(warnings),
        )

    def _record_provider(
        self,
        provider: object,
        operation: str,
        outcome: str,
        duration_seconds: float,
        exc: BaseException | None = None,
    ) -> None:
        if self.recorder is None:
            return
        try:
            self.recorder.record_provider(
                provider_label(provider),
                operation,
                outcome,
                duration_seconds,
                error_category=classify_error(exc),
            )
        except Exception:
            return

    def _record_stage(
        self,
        stage: str,
        outcome: str,
        duration_seconds: float,
        exc: BaseException | None = None,
    ) -> None:
        if self.recorder is None:
            return
        try:
            self.recorder.record_rag_stage(
                stage,
                outcome,
                duration_seconds,
                error_category=classify_error(exc),
            )
        except Exception:
            return

    @staticmethod
    def _validated_rerank(
        fused: list[RetrievalHit], ordering: list[RerankResult]
    ) -> list[RetrievalHit]:
        reranked: list[RetrievalHit] = []
        seen: set[int] = set()
        for rank, item in enumerate(ordering, start=1):
            if item.index in seen or not 0 <= item.index < len(fused):
                raise ProviderResponseError("rerank", "invalid_result_index")
            if not isfinite(item.score) or not 0 <= item.score <= 1:
                raise ProviderResponseError("rerank", "invalid_result_score")
            seen.add(item.index)
            reranked.append(fused[item.index].with_score(item.score, rank, "rerank"))
        if not reranked:
            raise ProviderResponseError("rerank", "empty_results")
        return reranked


def _elapsed_ms(started: float) -> float:
    return round((perf_counter() - started) * 1000, 3)


def _elapsed_seconds(started: float) -> float:
    return max(0.0, perf_counter() - started)


def _rerank_error_code(exc: Exception) -> str:
    if isinstance(exc, ProviderUnavailableError):
        if exc.reason == "API key is not configured":
            return "missing_credentials"
        if re.fullmatch(r"http_status_[1-5][0-9]{2}", exc.reason):
            return exc.reason
        if exc.reason in {"request_timeout", "transport_error"}:
            return exc.reason
        return "provider_unavailable"
    if isinstance(exc, ProviderResponseError):
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", exc.reason):
            return exc.reason
        return "invalid_response"
    return f"unexpected_{_class_name(exc)}"


def _class_name(value: object) -> str:
    name = type(value).__name__
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
