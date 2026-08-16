from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from app.bm25 import BM25Document, BM25Index
from app.embedding import DeterministicEmbeddingProvider
from app.providers import ProviderResponseError, ProviderUnavailableError
from app.rerank import (
    DeterministicRerankProvider,
    NoRerankProvider,
    RemoteRerankProvider,
    RerankResponse,
    RerankResult,
)
from app.retrieval import RetrievalConfig, RetrievalEngine, RetrievalMode
from app.retrieval.engine import RerankFailurePolicy
from app.vector_store import InMemoryVectorStore, VectorPoint


@pytest.mark.asyncio
async def test_remote_rerank_success_has_explicit_timeout_and_safe_usage() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.5},
                ],
                "meta": {
                    "billed_units": {"search_units": 1},
                    "provider_message": "must-not-be-persisted",
                },
                "usage": {"input_tokens": 12, "request_id": "must-not-be-persisted"},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key=" secret-token ",
            model_name="rerank-model",
            timeout_seconds=7.5,
            client=client,
        )
        response = await provider.rerank("query", ["first", "second"], 2)

    assert response.results == (RerankResult(1, 0.9), RerankResult(0, 0.5))
    assert response.usage == {"search_units": 1, "input_tokens": 12}
    assert response.cost is None
    assert response.cost_measurement == "not_available"
    assert requests[0].headers["Authorization"] == "Bearer secret-token"
    timeout = requests[0].extensions["timeout"]
    assert timeout == {"connect": 7.5, "read": 7.5, "write": 7.5, "pool": 7.5}


@pytest.mark.asyncio
async def test_remote_rerank_blank_key_does_not_make_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"results": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key=" \t ",
            model_name="rerank-model",
            client=client,
        )
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.rerank("query", ["document"], 1)

    assert exc_info.value.reason == "API key is not configured"
    assert requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("handler", "error_type", "reason"),
    [
        (
            lambda request: (_ for _ in ()).throw(
                httpx.ReadTimeout("secret-token", request=request)
            ),
            ProviderUnavailableError,
            "request_timeout",
        ),
        (
            lambda request: httpx.Response(
                401,
                text="Authorization Bearer secret-token private-response-body",
            ),
            ProviderUnavailableError,
            "http_status_401",
        ),
        (
            lambda request: httpx.Response(200, content=b"secret-token invalid-json"),
            ProviderResponseError,
            "invalid_json",
        ),
    ],
)
async def test_remote_rerank_errors_are_stable_and_redacted(
    handler: Callable[[httpx.Request], httpx.Response],
    error_type: type[Exception],
    reason: str,
) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key="secret-token",
            model_name="rerank-model",
            client=client,
        )
        with pytest.raises(error_type) as exc_info:
            await provider.rerank("query", ["document"], 1)

    assert exc_info.value.reason == reason
    error = str(exc_info.value)
    assert "secret-token" not in error
    assert "private-response-body" not in error


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [429, 500, 503])
async def test_remote_rerank_http_failure_codes_are_preserved(status_code: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, text="provider body must not escape")
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key="secret-token",
            model_name="rerank-model",
            client=client,
        )
        with pytest.raises(ProviderUnavailableError) as exc_info:
            await provider.rerank("query", ["document"], 1)

    assert exc_info.value.reason == f"http_status_{status_code}"
    assert "provider body" not in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "results",
    [
        [{"index": -1, "relevance_score": 0.8}],
        [{"index": 1.5, "relevance_score": 0.8}],
        [{"index": True, "relevance_score": 0.8}],
        [
            {"index": 0, "relevance_score": 0.8},
            {"index": 0, "relevance_score": 0.7},
        ],
        [{"index": 0, "relevance_score": "0.8"}],
        [{"index": 0, "relevance_score": 1.1}],
        [],
    ],
)
async def test_remote_rerank_rejects_invalid_results(results: list[object]) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"results": results}))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key="secret-token",
            model_name="rerank-model",
            client=client,
        )
        with pytest.raises(ProviderResponseError):
            await provider.rerank("query", ["first", "second"], 2)


@pytest.mark.asyncio
async def test_remote_rerank_rejects_non_finite_score() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            content=b'{"results":[{"index":0,"relevance_score":NaN}]}',
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        provider = RemoteRerankProvider(
            base_url="https://rerank.example/v2",
            api_key="secret-token",
            model_name="rerank-model",
            client=client,
        )
        with pytest.raises(ProviderResponseError, match="invalid_result_score"):
            await provider.rerank("query", ["first", "second"], 2)


class FailingRerankProvider:
    provider_name = "remote"
    model_name = "rerank-model"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> list[RerankResult]:
        del query, documents, top_k
        raise ProviderUnavailableError(
            "remote_rerank", "upstream private-response-body secret-token"
        )


class MetadataRerankProvider:
    provider_name = "remote"
    model_name = "rerank-model"

    async def rerank(self, query: str, documents: list[str], top_k: int) -> RerankResponse:
        del query
        return RerankResponse(
            tuple(
                RerankResult(index, 1.0 - index / 10) for index in range(min(top_k, len(documents)))
            ),
            usage={"search_units": 1},
            cost=None,
            cost_measurement="not_available",
        )


async def _engine(
    rerank_provider: object,
    *,
    failure_policy: RerankFailurePolicy = RerankFailurePolicy.OPEN,
    count: int = 3,
    limits: int = 3,
) -> RetrievalEngine:
    embedding = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    bm25 = BM25Index()
    documents = [
        BM25Document(
            f"chunk-{index}",
            f"document-{index}",
            f"Policy {index}",
            f"common policy evidence {index}",
            f"https://example.gov/{index}",
            {},
        )
        for index in range(count)
    ]
    bm25.rebuild(documents)
    await vector_store.ensure_collection(8)
    await vector_store.upsert(
        [
            VectorPoint(
                document.chunk_id,
                await embedding.embed_query(document.content),
                document.document_id,
                document.content,
                document.title,
                document.source_url,
            )
            for document in documents
        ]
    )
    return RetrievalEngine(
        bm25_index=bm25,
        embedding_provider=embedding,
        vector_store=vector_store,
        rerank_provider=rerank_provider,  # type: ignore[arg-type]
        config=RetrievalConfig(
            bm25_top_k=limits,
            vector_top_k=limits,
            rerank_top_k=limits,
            final_top_k=limits,
            rerank_failure_policy=failure_policy,
        ),
    )


@pytest.mark.asyncio
async def test_rerank_fail_open_preserves_fusion_order_and_redacts_error() -> None:
    engine = await _engine(FailingRerankProvider())

    trace = await engine.search("common policy", mode=RetrievalMode.HYBRID_RERANK)

    assert [hit.chunk_id for hit in trace.final_results] == [
        hit.chunk_id for hit in trace.fusion_results[:3]
    ]
    assert trace.rerank_results == ()
    assert trace.rerank_metadata["applied"] is False
    assert trace.rerank_metadata["error"] == "provider_unavailable"
    assert trace.rerank_metadata["error_code"] == "provider_unavailable"
    assert trace.rerank_metadata["candidate_count"] == len(trace.fusion_results)
    assert trace.rerank_metadata["reranked_count"] == 0
    assert trace.rerank_metadata["cost"] is None
    assert trace.rerank_metadata["cost_measurement"] == "not_available"
    serialized = json.dumps(trace.rerank_metadata)
    assert "secret-token" not in serialized
    assert "private-response-body" not in serialized
    assert trace.warnings == ("rerank_failed_open:provider_unavailable",)


@pytest.mark.asyncio
async def test_rerank_fail_closed_raises_provider_error() -> None:
    engine = await _engine(FailingRerankProvider(), failure_policy=RerankFailurePolicy.CLOSED)

    with pytest.raises(ProviderUnavailableError):
        await engine.search("common policy", mode=RetrievalMode.HYBRID_RERANK)


@pytest.mark.asyncio
async def test_remote_rerank_execution_metadata_is_complete() -> None:
    engine = await _engine(MetadataRerankProvider())

    trace = await engine.search("common policy", mode=RetrievalMode.HYBRID_RERANK)

    assert trace.rerank_metadata == {
        "applied": True,
        "provider": "remote",
        "model": "rerank-model",
        "failure_policy": "open",
        "error": None,
        "error_code": None,
        "candidate_count": len(trace.fusion_results),
        "reranked_count": len(trace.rerank_results),
        "latency_ms": trace.rerank_metadata["latency_ms"],
        "usage": {"search_units": 1},
        "cost": None,
        "cost_measurement": "not_available",
    }


@pytest.mark.asyncio
async def test_disabled_and_deterministic_cost_semantics_are_explicit() -> None:
    disabled_trace = await (await _engine(NoRerankProvider())).search(
        "common policy", mode=RetrievalMode.HYBRID_RERANK
    )
    deterministic_trace = await (await _engine(DeterministicRerankProvider())).search(
        "common policy", mode=RetrievalMode.HYBRID_RERANK
    )

    assert disabled_trace.rerank_metadata["applied"] is False
    assert disabled_trace.rerank_metadata["provider"] == "none"
    assert disabled_trace.rerank_metadata["cost"] is None
    assert disabled_trace.rerank_metadata["cost_measurement"] == "not_applicable"
    assert deterministic_trace.rerank_metadata["applied"] is True
    assert deterministic_trace.rerank_metadata["provider"] == "deterministic"
    assert deterministic_trace.rerank_metadata["cost"] is None
    assert deterministic_trace.rerank_metadata["cost_measurement"] == "not_applicable"


@pytest.mark.asyncio
async def test_explicit_top_k_expands_candidate_pool_and_final_slice() -> None:
    engine = await _engine(DeterministicRerankProvider(), count=5, limits=1)

    trace = await engine.search("common policy", mode=RetrievalMode.HYBRID_RERANK, top_k=4)

    assert len(trace.bm25_results) == 4
    assert len(trace.vector_results) == 4
    assert len(trace.fusion_results) == 4
    assert len(trace.rerank_results) == 4
    assert len(trace.final_results) == 4
    assert trace.config.bm25_top_k == 4
    assert trace.config.vector_top_k == 4
    assert trace.config.rerank_top_k == 4
    assert trace.config.final_top_k == 4
    assert trace.rerank_metadata["candidate_count"] == 4


@pytest.mark.asyncio
@pytest.mark.parametrize("top_k", [0, -1, 201])
async def test_explicit_top_k_rejects_invalid_limits(top_k: int) -> None:
    engine = await _engine(DeterministicRerankProvider())

    with pytest.raises(ValueError, match="top_k"):
        await engine.search("common policy", top_k=top_k)
