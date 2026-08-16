from __future__ import annotations

import httpx
import pytest

from app.bm25 import BM25Document, BM25Index
from app.cache import InMemoryEmbeddingCache
from app.embedding import (
    CachedQueryEmbeddingProvider,
    DeterministicEmbeddingProvider,
    EmbeddingBatcher,
    RemoteEmbeddingProvider,
)
from app.providers import ProviderUnavailableError
from app.rerank import DeterministicRerankProvider
from app.retrieval import RetrievalEngine, RetrievalMode
from app.vector_store import InMemoryVectorStore, VectorPoint


@pytest.mark.asyncio
async def test_remote_embedding_reports_missing_credentials() -> None:
    provider = RemoteEmbeddingProvider(
        base_url="https://example.invalid/v1", api_key=None, model_name="model"
    )
    with pytest.raises(ProviderUnavailableError) as exc_info:
        await provider.embed_query("query")

    assert exc_info.value.provider == "remote_embedding"
    assert exc_info.value.reason == "API key is not configured"


@pytest.mark.asyncio
async def test_remote_embedding_blank_credentials_do_not_make_a_request() -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        provider = RemoteEmbeddingProvider(
            base_url="https://example.test/v1",
            api_key="  \t ",
            model_name="model",
            client=client,
        )
        with pytest.raises(ProviderUnavailableError, match="API key is not configured"):
            await provider.embed_documents(["query"])

    assert calls == []


@pytest.mark.asyncio
async def test_missing_remote_embedding_does_not_fallback_or_populate_cache() -> None:
    cache = InMemoryEmbeddingCache()
    provider = RemoteEmbeddingProvider(
        base_url="https://example.invalid/v1", api_key=None, model_name="model"
    )
    batcher = EmbeddingBatcher(provider, cache, batch_size=2)

    with pytest.raises(ProviderUnavailableError, match="API key is not configured"):
        await batcher.embed(["document text"])

    assert cache.values == {}


@pytest.mark.asyncio
async def test_deterministic_embedding_is_explicit_and_stable() -> None:
    provider = DeterministicEmbeddingProvider(dimensions=8)

    first = await provider.embed_query("same input")
    second = await provider.embed_query("same input")
    documents = await provider.embed_documents(["same input", "other input"])

    assert provider.provider_name == "deterministic"
    assert provider.model_name == "deterministic-sha256-v1"
    assert first == second == documents[0]
    assert len(first) == 8
    assert all(-1.0 <= value <= 1.0 for value in first)
    assert len(documents[1]) == 8
    assert documents[1] != first


@pytest.mark.asyncio
async def test_remote_embedding_validates_response_count() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json={"data": []}))
    async with httpx.AsyncClient(transport=transport) as client:
        provider = RemoteEmbeddingProvider(
            base_url="https://example.test/v1", api_key="secret", model_name="model", client=client
        )
        with pytest.raises(Exception, match="embedding count"):
            await provider.embed_query("query")


@pytest.mark.asyncio
async def test_query_embedding_cache_is_versioned_and_reused() -> None:
    class CountingProvider(DeterministicEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(dimensions=8)
            self.query_calls = 0

        async def embed_query(self, text: str) -> list[float]:
            self.query_calls += 1
            return await super().embed_query(text)

    cache = InMemoryEmbeddingCache()
    provider = CountingProvider()
    cached = CachedQueryEmbeddingProvider(provider, cache, version="v-test")

    first = await cached.embed_query("normalized query")
    second = await cached.embed_query("normalized query")

    assert first == second
    assert provider.query_calls == 1
    assert len(cache.values) == 1
    assert next(iter(cache.values)).startswith(
        "query-embedding:deterministic:deterministic-sha256-v1:"
    )
    assert ":v-test:" in next(iter(cache.values))


@pytest.mark.asyncio
async def test_concurrent_query_embedding_requests_are_coalesced() -> None:
    class CountingProvider(DeterministicEmbeddingProvider):
        def __init__(self) -> None:
            super().__init__(dimensions=8)
            self.query_calls = 0

        async def embed_query(self, text: str) -> list[float]:
            self.query_calls += 1
            await __import__("asyncio").sleep(0)
            return await super().embed_query(text)

    provider = CountingProvider()
    cached = CachedQueryEmbeddingProvider(
        provider,
        InMemoryEmbeddingCache(),
        version="v-test",
    )

    first, second = await __import__("asyncio").gather(
        cached.embed_query("same query"),
        cached.embed_query("same query"),
    )

    assert first == second
    assert provider.query_calls == 1


@pytest.mark.asyncio
async def test_query_embedding_cache_separates_compatible_endpoints() -> None:
    class EndpointProvider(DeterministicEmbeddingProvider):
        provider_name = "remote"
        model_name = "shared-model"

        def __init__(self, base_url: str) -> None:
            super().__init__(dimensions=8)
            self.base_url = base_url
            self.query_calls = 0

        async def embed_query(self, text: str) -> list[float]:
            self.query_calls += 1
            return await super().embed_query(text)

    cache = InMemoryEmbeddingCache()
    first_provider = EndpointProvider("https://first.example/v1")
    second_provider = EndpointProvider("https://second.example/v1")

    await CachedQueryEmbeddingProvider(first_provider, cache, version="v1").embed_query(
        "same query"
    )
    await CachedQueryEmbeddingProvider(second_provider, cache, version="v1").embed_query(
        "same query"
    )

    assert first_provider.query_calls == 1
    assert second_provider.query_calls == 1
    assert len(cache.values) == 2


@pytest.mark.asyncio
async def test_query_embedding_cache_failure_falls_back_to_provider() -> None:
    class UnavailableCache:
        async def get(self, key: str) -> list[float] | None:
            del key
            raise RuntimeError("cache unavailable")

        async def set(self, key: str, vector: list[float]) -> None:
            del key, vector
            raise RuntimeError("cache unavailable")

    provider = DeterministicEmbeddingProvider(dimensions=8)
    cached = CachedQueryEmbeddingProvider(provider, UnavailableCache(), version="v-test")

    assert await cached.embed_query("query") == await provider.embed_query("query")


@pytest.mark.asyncio
async def test_hybrid_retrieval_runs_full_trace() -> None:
    embedding = DeterministicEmbeddingProvider(dimensions=8)
    vector_store = InMemoryVectorStore()
    content = "四川软件产业政策提供研发资金支持"
    await vector_store.upsert(
        [
            VectorPoint(
                "chunk-1",
                await embedding.embed_query(content),
                "doc-1",
                content,
                "软件政策",
                "https://example.gov/1",
                {"region": "四川"},
            )
        ]
    )
    bm25 = BM25Index()
    bm25.rebuild(
        [
            BM25Document(
                "chunk-1", "doc-1", "软件政策", content, "https://example.gov/1", {"region": "四川"}
            )
        ]
    )
    engine = RetrievalEngine(
        bm25_index=bm25,
        embedding_provider=embedding,
        vector_store=vector_store,
        rerank_provider=DeterministicRerankProvider(),
    )
    trace = await engine.search(
        "四川软件资金支持", mode=RetrievalMode.HYBRID_RERANK, filters={"region": "四川"}
    )
    assert trace.bm25_results
    assert trace.vector_results
    assert trace.fusion_results
    assert trace.rerank_results
    assert trace.final_results[0].chunk_id == "chunk-1"
