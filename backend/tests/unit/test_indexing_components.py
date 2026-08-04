from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.bm25 import BM25Document, BM25Index
from app.cache import InMemoryEmbeddingCache
from app.chunking import load_chunking_config
from app.embedding import EmbeddingBatcher
from app.providers import ProviderResponseError, ProviderUnavailableError
from app.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorPoint


class FlakyEmbeddingProvider:
    provider_name = "flaky"
    model_name = "flaky-v1"

    def __init__(self) -> None:
        self.calls = 0

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.calls == 1:
            raise ProviderUnavailableError("flaky", "temporary failure")
        return [[float(len(text)), 1.0, 0.0, -1.0] for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return (await self.embed_documents([text]))[0]


def _artifact_path(name: str) -> Path:
    path = Path(".test-data") / "phase5" / f"{uuid4()}-{name}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def test_chunking_config_loads_direct_yaml() -> None:
    path = _artifact_path("chunking.yaml")
    path.write_text(
        "target_chars: 50\nmin_chars: 10\nmax_chars: 80\noverlap_chars: 5\n",
        encoding="utf-8",
    )
    config = load_chunking_config(path)
    assert config.target_chars == 50
    assert config.overlap_chars == 5


@pytest.mark.asyncio
async def test_embedding_batcher_retries_and_uses_versioned_cache() -> None:
    provider = FlakyEmbeddingProvider()
    batcher = EmbeddingBatcher(
        provider,
        InMemoryEmbeddingCache(),
        batch_size=2,
        cost_per_1k_chars=0.5,
        version="2026-08",
    )
    first = await batcher.embed(["alpha", "beta"])
    second = await batcher.embed(["alpha", "beta"])
    assert provider.calls == 2
    assert first.embedded_count == 2
    assert first.estimated_cost == pytest.approx(0.0045)
    assert second.cache_hits == 2
    assert second.embedded_count == 0


@pytest.mark.asyncio
async def test_in_memory_vector_store_supports_range_filters() -> None:
    store = InMemoryVectorStore()
    await store.ensure_collection(4)
    await store.upsert(
        [
            VectorPoint(
                "one",
                [1.0, 0.0, 0.0, 0.0],
                "doc-one",
                "content",
                "title",
                "https://example.gov/one",
                {"publish_date": "2026-01-01", "region": "四川"},
            ),
            VectorPoint(
                "two",
                [0.8, 0.2, 0.0, 0.0],
                "doc-two",
                "content",
                "title",
                "https://example.gov/two",
                {"publish_date": "2024-01-01", "region": "四川"},
            ),
        ]
    )
    hits = await store.search(
        [1.0, 0.0, 0.0, 0.0],
        5,
        {
            "document_id": "doc-one",
            "region": "四川",
            "publish_date_gte": "2025-01-01",
        },
    )
    assert [hit.chunk_id for hit in hits] == ["one"]


def test_bm25_snapshot_round_trip() -> None:
    path = _artifact_path("bm25.json")
    index = BM25Index()
    index.rebuild(
        [
            BM25Document(
                "chunk-1",
                "document-1",
                "软件政策",
                "支持企业研发投入",
                "https://example.gov/policy",
                {"region": "四川", "document_version": 2},
            )
        ]
    )
    index.save(path)
    restored = BM25Index.load(path)
    hits = restored.search("软件研发", 5, {"region": "四川"})
    assert restored.document_count == 1
    assert hits[0].chunk_id == "chunk-1"


@pytest.mark.asyncio
async def test_qdrant_collection_creation_and_payload_indexes(monkeypatch) -> None:
    created_indexes: list[str] = []

    class FakeClient:
        async def collection_exists(self, _collection_name: str) -> bool:
            return False

        async def create_collection(self, **kwargs) -> bool:
            assert kwargs["vectors_config"].size == 8
            return True

        async def get_collection(self, _collection_name: str):
            return SimpleNamespace(
                config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=8))),
                payload_schema={},
            )

        async def create_payload_index(self, **kwargs):
            created_indexes.append(str(kwargs["field_name"]))

        async def close(self) -> None:
            return None

    store = QdrantVectorStore(url="http://qdrant.test", collection_name="chunks")
    monkeypatch.setattr(store, "_client", lambda: FakeClient())
    await store.ensure_collection(8)
    assert {"document_id", "source_id", "publish_date"}.issubset(created_indexes)


@pytest.mark.asyncio
async def test_qdrant_upsert_search_filters_and_delete_contract(monkeypatch) -> None:
    calls: dict[str, object] = {}

    class FakeClient:
        async def upsert(self, collection_name: str, *, points, wait: bool) -> None:
            calls["upsert"] = (collection_name, points, wait)

        async def query_points(self, **kwargs):
            calls["query"] = kwargs
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        id="point-1",
                        score=0.9,
                        payload={
                            "document_id": "doc-1",
                            "content": "研发资金支持",
                            "title": "政策",
                            "source_url": "https://example.gov/policy",
                            "region": "四川",
                        },
                    )
                ]
            )

        async def delete(self, collection_name: str, selector, *, wait: bool) -> None:
            calls["delete"] = (collection_name, selector.points, wait)

        async def close(self) -> None:
            return None

    fake = FakeClient()
    store = QdrantVectorStore(url="http://qdrant.test", collection_name="chunks")
    monkeypatch.setattr(store, "_client", lambda: fake)
    await store.upsert(
        [
            VectorPoint(
                "point-1",
                [1.0, 0.0, 0.0, 0.0],
                "doc-1",
                "研发资金支持",
                "政策",
                "https://example.gov/policy",
                {"region": "四川"},
            )
        ]
    )
    hits = await store.search(
        [1.0, 0.0, 0.0, 0.0],
        5,
        {"region": "四川", "publish_date_gte": "2025-01-01"},
    )
    await store.delete(["point-1"])
    assert hits[0].document_id == "doc-1"
    assert calls["upsert"]
    assert calls["query"]
    assert calls["delete"] == ("chunks", ["point-1"], True)


@pytest.mark.asyncio
async def test_qdrant_rejects_existing_dimension_mismatch(monkeypatch) -> None:
    class FakeClient:
        async def collection_exists(self, _collection_name: str) -> bool:
            return True

        async def get_collection(self, _collection_name: str):
            return SimpleNamespace(
                config=SimpleNamespace(params=SimpleNamespace(vectors=SimpleNamespace(size=4))),
                payload_schema={},
            )

        async def close(self) -> None:
            return None

    store = QdrantVectorStore(url="http://qdrant.test", collection_name="chunks")
    monkeypatch.setattr(store, "_client", lambda: FakeClient())
    with pytest.raises(ProviderResponseError, match="expected 8"):
        await store.ensure_collection(8)
