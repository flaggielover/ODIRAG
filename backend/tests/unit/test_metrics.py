from __future__ import annotations

import pytest

from app.bm25 import BM25Index
from app.embedding import DeterministicEmbeddingProvider, RemoteEmbeddingProvider
from app.metrics import MetricsRegistry, provider_label
from app.providers import ProviderUnavailableError
from app.rerank import NoRerankProvider
from app.retrieval import RetrievalEngine, RetrievalMode
from app.vector_store import InMemoryVectorStore


async def test_metrics_registry_reports_bounded_latency_percentiles() -> None:
    registry = MetricsRegistry()
    for duration_ms in (10, 20, 30, 40, 100):
        await registry.record("POST", "/api/chat", 200, duration_ms / 1000)
    for duration_ms in (1, 2, 3, 4, 10):
        registry.record_database(duration_ms / 1000)

    snapshot = await registry.snapshot()
    route = snapshot["routes"][0]
    database = snapshot["database_latency"]

    assert route["sample_count"] == 5
    assert route["p50_latency_ms"] == 30
    assert route["p95_latency_ms"] == 100
    assert route["p99_latency_ms"] == 100
    assert database["sample_count"] == 5
    assert database["p50_latency_ms"] == 3
    assert database["p95_latency_ms"] == 10


async def test_prometheus_registry_uses_bounded_safe_labels() -> None:
    registry = MetricsRegistry()
    await registry.record("GET", "/api/documents/{document_id}", 200, 0.025)
    registry.record_http_in_flight("GET", "/api/documents/{document_id}", 1)
    registry.record_http_in_flight("GET", "/api/documents/{document_id}", -1)
    registry.record_provider(
        "remote",
        "embed_query",
        "error",
        0.05,
        error_category="missing_credentials",
    )
    registry.record_provider(
        "provider=secret-value",
        "embed_query",
        "error",
        0.01,
        error_category="not-a-bounded-category",
    )
    registry.record_rag_stage("embedding", "error", 0.05, error_category="timeout")
    registry.record_rag_request(
        "refusal",
        0.3,
        refusal_reason="insufficient_evidence_relevance",
        candidate_counts={"retrieved": 8, "reranked": 5, "final": 5},
    )
    registry.record_rag_request("success", 1.2, grounded=True)
    registry.record_http_exception("/api/chat", "unexpected")

    payload = registry.prometheus_payload().decode("utf-8")

    assert "odirag_http_requests_total" in payload
    assert 'route="/api/documents/{document_id}"' in payload
    assert 'status_class="2xx"' in payload
    assert "odirag_http_requests_in_flight" in payload
    assert "odirag_provider_requests_total" in payload
    assert 'operation="embed_query"' in payload
    assert 'error_category="missing_credentials"' in payload
    assert "odirag_rag_stage_total" in payload
    assert 'stage="embedding"' in payload
    assert 'odirag_rag_requests_total{status="refusal"} 1.0' in payload
    assert "odirag_rag_grounded_answers_total 1.0" in payload
    assert 'odirag_rag_refusals_total{reason="insufficient_evidence_relevance"} 1.0' in payload
    assert 'odirag_rag_candidate_count_count{stage="retrieved"} 1.0' in payload
    assert (
        'odirag_http_exceptions_total{error_category="unexpected",route="/api/chat"} 1.0' in payload
    )
    assert "secret-value" not in payload
    assert "not-a-bounded-category" not in payload


def test_provider_label_uses_wrapped_openai_compatible_endpoint() -> None:
    class CachedProvider:
        provider_name = "remote"

        def __init__(self) -> None:
            self.provider = RemoteEmbeddingProvider(
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
                api_key="not-exported",
                model_name="text-embedding-v4",
            )

    assert provider_label(CachedProvider()) == "bailian"


@pytest.mark.asyncio
async def test_embedding_failure_is_recorded_without_query_or_error_text() -> None:
    registry = MetricsRegistry()
    engine = RetrievalEngine(
        bm25_index=BM25Index(),
        embedding_provider=RemoteEmbeddingProvider(
            base_url="https://example.invalid/v1",
            api_key=None,
            model_name="model",
        ),
        vector_store=InMemoryVectorStore(),
        rerank_provider=NoRerankProvider(),
        recorder=registry,
    )
    query = "do-not-export-this-query"

    with pytest.raises(ProviderUnavailableError, match="API key is not configured"):
        await engine.search(query, mode=RetrievalMode.VECTOR)

    payload = registry.prometheus_payload().decode("utf-8")
    assert 'provider="remote"' in payload
    assert 'operation="embed_query"' in payload
    assert 'outcome="error"' in payload
    assert 'error_category="missing_credentials"' in payload
    assert 'stage="embedding"' in payload
    assert query not in payload
    assert "API key is not configured" not in payload


@pytest.mark.asyncio
async def test_optional_recorder_failure_does_not_break_retrieval() -> None:
    class FailingRecorder:
        def record_provider(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("metrics backend failed")

        def record_rag_stage(self, *_args: object, **_kwargs: object) -> None:
            raise RuntimeError("metrics backend failed")

    engine = RetrievalEngine(
        bm25_index=BM25Index(),
        embedding_provider=DeterministicEmbeddingProvider(dimensions=8),
        vector_store=InMemoryVectorStore(),
        rerank_provider=NoRerankProvider(),
        recorder=FailingRecorder(),
    )

    trace = await engine.search("safe query", mode=RetrievalMode.VECTOR)

    assert trace.vector_results == ()
