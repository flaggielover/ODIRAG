from __future__ import annotations

import pytest

from app.bm25 import BM25Document, BM25Index
from app.embedding import DeterministicEmbeddingProvider
from app.providers import ProviderResponseError
from app.rerank import NoRerankProvider, RerankResult
from app.retrieval import (
    RetrievalConfig,
    RetrievalEngine,
    RetrievalMode,
    RetrievalQueryAnalyzer,
)
from app.vector_store import InMemoryVectorStore, VectorPoint


class InvalidRerankProvider:
    model_name = "invalid"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        del query, documents, top_k
        return [RerankResult(0, 0.8), RerankResult(0, 0.7)]


def test_query_analysis_infers_dates_and_canonical_region() -> None:
    analysis = RetrievalQueryAnalyzer().analyze(
        "Sichuan 2025之后的软件政策",
        {"document_type": "产业政策"},
    )
    assert analysis.inferred_filters == {
        "publish_date_gte": "2026-01-01",
        "region": "四川",
    }
    assert analysis.applied_filters["document_type"] == "产业政策"
    with pytest.raises(ValueError, match="unsupported metadata filters"):
        RetrievalQueryAnalyzer().analyze("政策", {"unknown": "value"})


@pytest.mark.asyncio
async def test_all_retrieval_modes_emit_complete_trace() -> None:
    embedding = DeterministicEmbeddingProvider(dimensions=8)
    store = InMemoryVectorStore()
    content = "四川软件企业研发资金支持"
    await store.ensure_collection(8)
    await store.upsert(
        [
            VectorPoint(
                "chunk-1",
                await embedding.embed_query(content),
                "document-1",
                content,
                "软件政策",
                "https://example.gov/policy",
                {"region": "四川", "publish_date": "2026-02-01"},
            )
        ]
    )
    bm25 = BM25Index()
    bm25.rebuild(
        [
            BM25Document(
                "chunk-1",
                "document-1",
                "软件政策",
                content,
                "https://example.gov/policy",
                {"region": "四川", "publish_date": "2026-02-01"},
            )
        ]
    )
    engine = RetrievalEngine(
        bm25_index=bm25,
        embedding_provider=embedding,
        vector_store=store,
        rerank_provider=NoRerankProvider(),
        config=RetrievalConfig(final_top_k=3),
    )
    for mode in RetrievalMode:
        trace = await engine.search(
            content,
            mode=mode,
            filters={"publish_date_gte": "2026-01-01"},
        )
        assert trace.trace_id
        assert trace.final_results
        assert trace.timings_ms["total"] >= 0
        assert trace.analysis.applied_filters["region"] == "四川"
        if mode is RetrievalMode.HYBRID_RERANK:
            assert trace.warnings == ("rerank_provider_disabled",)


@pytest.mark.asyncio
async def test_invalid_rerank_response_is_rejected() -> None:
    embedding = DeterministicEmbeddingProvider(dimensions=8)
    store = InMemoryVectorStore()
    content = "软件研发支持"
    await store.upsert(
        [
            VectorPoint(
                "chunk-1",
                await embedding.embed_query(content),
                "document-1",
                content,
                "政策",
                "https://example.gov/policy",
            )
        ]
    )
    bm25 = BM25Index()
    bm25.rebuild(
        [
            BM25Document(
                "chunk-1",
                "document-1",
                "政策",
                content,
                "https://example.gov/policy",
                {},
            )
        ]
    )
    engine = RetrievalEngine(
        bm25_index=bm25,
        embedding_provider=embedding,
        vector_store=store,
        rerank_provider=InvalidRerankProvider(),
    )
    with pytest.raises(ProviderResponseError, match="indices"):
        await engine.search("软件研发", mode=RetrievalMode.HYBRID_RERANK)
