from __future__ import annotations

import httpx
import pytest

from app.bm25 import BM25Document, BM25Index
from app.embedding import DeterministicEmbeddingProvider, RemoteEmbeddingProvider
from app.providers import ProviderUnavailableError
from app.rerank import DeterministicRerankProvider
from app.retrieval import RetrievalEngine, RetrievalMode
from app.vector_store import InMemoryVectorStore, VectorPoint


@pytest.mark.asyncio
async def test_remote_embedding_reports_missing_credentials() -> None:
    provider = RemoteEmbeddingProvider(
        base_url="https://example.invalid/v1", api_key=None, model_name="model"
    )
    with pytest.raises(ProviderUnavailableError):
        await provider.embed_query("query")


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
