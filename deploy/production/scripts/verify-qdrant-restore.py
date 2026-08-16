from __future__ import annotations

import asyncio
import hashlib
import sys
from time import perf_counter
from urllib.parse import urlsplit

from app.config import get_settings
from app.database import DatabaseManager
from app.retrieval import RetrievalEngine, RetrievalMode
from app.runtime import build_application_runtime
from app.vector_store import QdrantVectorStore
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

ACTIVE_COLLECTION = "odirag_chunks_bailian_v4"
ROLLBACK_COLLECTION = "odirag_chunks"
TEMP_PREFIX = f"{ACTIVE_COLLECTION}_restore_test_"
EXPECTED_POINTS = 821
EXPECTED_DIMENSIONS = 1536
QUERY = "\u8f6f\u4ef6\u4f01\u4e1a\u7814\u53d1\u6295\u5165\u652f\u6301\u63aa\u65bd"


class VerificationError(RuntimeError):
    pass


class FixedQueryEmbeddingProvider:
    provider_name = "remote"

    def __init__(self, model_name: str, vector: list[float]) -> None:
        self.model_name = model_name
        self._vector = vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vector) for _ in texts]

    async def embed_query(self, text_value: str) -> list[float]:
        del text_value
        return list(self._vector)


def _validate_temp_collection(collection: str) -> None:
    if not collection.startswith(TEMP_PREFIX):
        raise VerificationError("invalid_temporary_collection_name")
    suffix = collection.removeprefix(TEMP_PREFIX)
    if not suffix or any(character not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_-" for character in suffix):
        raise VerificationError("invalid_temporary_collection_suffix")


def _api_key() -> str | None:
    settings = get_settings()
    return settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None


async def _client() -> AsyncQdrantClient:
    settings = get_settings()
    return AsyncQdrantClient(url=settings.qdrant_url, api_key=_api_key())


async def preflight(collection: str) -> None:
    _validate_temp_collection(collection)
    client = await _client()
    try:
        if not await client.collection_exists(ACTIVE_COLLECTION):
            raise VerificationError("active_collection_missing")
        if not await client.collection_exists(ROLLBACK_COLLECTION):
            raise VerificationError("rollback_collection_missing")
        if await client.collection_exists(collection):
            raise VerificationError("temporary_collection_already_exists")
    finally:
        await client.close()
    print("qdrant_restore_preflight=PASS-LIVE active=true rollback=true temporary_absent=true")


def _vector_shape(info: object) -> tuple[int, str]:
    vectors = info.config.params.vectors  # type: ignore[attr-defined]
    if isinstance(vectors, dict):
        if len(vectors) != 1:
            raise VerificationError("unexpected_named_vectors")
        vectors = next(iter(vectors.values()))
    dimensions = int(vectors.size)
    distance_value = getattr(vectors.distance, "value", str(vectors.distance))
    return dimensions, str(distance_value)


async def _payload_ids(client: AsyncQdrantClient, collection: str) -> tuple[list[str], int]:
    offset = None
    payload_ids: list[str] = []
    point_payload_mismatches = 0
    while True:
        points, offset = await client.scroll(
            collection_name=collection,
            limit=256,
            offset=offset,
            with_payload=["chunk_id"],
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            chunk_id = payload.get("chunk_id")
            if not isinstance(chunk_id, str) or not chunk_id:
                raise VerificationError("missing_payload_chunk_id")
            payload_ids.append(chunk_id)
            if str(point.id) != chunk_id:
                point_payload_mismatches += 1
        if offset is None:
            return payload_ids, point_payload_mismatches


async def _postgres_ids() -> list[str]:
    settings = get_settings()
    database = DatabaseManager(settings)
    try:
        async with database.session_factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            result = await session.execute(text("SELECT chunk_id FROM chunks ORDER BY chunk_id"))
            return [str(value) for value in result.scalars().all()]
    finally:
        await database.dispose()


async def verify(collection: str) -> None:
    _validate_temp_collection(collection)
    settings = get_settings()
    client = await _client()
    runtime = None
    try:
        for _ in range(120):
            info = await client.get_collection(collection)
            status = getattr(info.status, "value", str(info.status)).lower()
            if status == "green":
                break
            await asyncio.sleep(1)
        else:
            raise VerificationError("restored_collection_not_green")

        dimensions, distance = _vector_shape(info)
        points_count = int(info.points_count or 0)
        if points_count != EXPECTED_POINTS or dimensions != EXPECTED_DIMENSIONS:
            raise VerificationError("restored_collection_shape_mismatch")
        if distance.lower() != "cosine":
            raise VerificationError("restored_collection_distance_mismatch")

        payload_ids, point_payload_mismatches = await _payload_ids(client, collection)
        postgres_ids = await _postgres_ids()
        duplicate_payload_ids = len(payload_ids) - len(set(payload_ids))
        duplicate_postgres_ids = len(postgres_ids) - len(set(postgres_ids))
        if len(payload_ids) != EXPECTED_POINTS or len(postgres_ids) != EXPECTED_POINTS:
            raise VerificationError("chunk_id_count_mismatch")
        if duplicate_payload_ids or duplicate_postgres_ids or point_payload_mismatches:
            raise VerificationError("chunk_id_uniqueness_mismatch")
        if set(payload_ids) != set(postgres_ids):
            raise VerificationError("postgres_qdrant_chunk_id_set_mismatch")
        chunk_ids_digest = hashlib.sha256(
            ("\n".join(sorted(payload_ids)) + "\n").encode("utf-8")
        ).hexdigest()

        endpoint = urlsplit(settings.embedding_base_url)
        if settings.embedding_provider != "remote" or endpoint.hostname != "dashscope.aliyuncs.com":
            raise VerificationError("unexpected_embedding_provider")
        if settings.embedding_model != "text-embedding-v4":
            raise VerificationError("unexpected_embedding_model")
        if settings.embedding_dimensions != EXPECTED_DIMENSIONS:
            raise VerificationError("unexpected_embedding_dimensions")

        runtime = build_application_runtime(settings)
        embedding_started = perf_counter()
        query_vector = await runtime.embedding_provider.embed_query(QUERY)
        embedding_latency_ms = round((perf_counter() - embedding_started) * 1000, 3)
        if len(query_vector) != EXPECTED_DIMENSIONS:
            raise VerificationError("query_embedding_dimension_mismatch")

        active_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=ACTIVE_COLLECTION,
            api_key=_api_key(),
        )
        restored_store = QdrantVectorStore(
            url=settings.qdrant_url,
            collection_name=collection,
            api_key=_api_key(),
        )
        active_hits = await active_store.search(query_vector, 10)
        restored_hits = await restored_store.search(query_vector, 10)
        active_ids = [hit.chunk_id for hit in active_hits]
        restored_ids = [hit.chunk_id for hit in restored_hits]
        if len(active_ids) != 10 or active_ids != restored_ids:
            raise VerificationError("active_restored_vector_results_mismatch")
        score_delta = max(
            abs(active.score - restored.score)
            for active, restored in zip(active_hits, restored_hits, strict=True)
        )
        if score_delta > 0.000001:
            raise VerificationError("active_restored_vector_score_mismatch")

        fixed_embedding = FixedQueryEmbeddingProvider(settings.embedding_model, query_vector)
        engine = RetrievalEngine(
            bm25_index=runtime.bm25_index,
            embedding_provider=fixed_embedding,
            vector_store=restored_store,
            rerank_provider=runtime.rerank_provider,
            config=runtime.retrieval_config,
        )
        trace = await engine.search(QUERY, mode=RetrievalMode.HYBRID_RERANK, top_k=5)
        if not trace.bm25_results or not trace.vector_results or not trace.final_results:
            raise VerificationError("hybrid_retrieval_missing_results")
        if trace.rerank_metadata.get("applied") is not True:
            raise VerificationError("cohere_rerank_not_applied")

        result_digest = hashlib.sha256("\n".join(restored_ids).encode("utf-8")).hexdigest()
        print(
            "qdrant_restore_integrity=PASS-LIVE "
            f"points={points_count} dimensions={dimensions} distance={distance} "
            f"postgres_ids={len(postgres_ids)} payload_ids={len(payload_ids)} "
            f"duplicate_payload_chunk_id={duplicate_payload_ids} id_set_equal=true "
            f"chunk_ids_sha256={chunk_ids_digest}"
        )
        print(
            "bailian_query_embedding=PASS-LIVE provider=remote "
            f"model={settings.embedding_model} latency_ms={embedding_latency_ms} "
            f"vector_length={len(query_vector)}"
        )
        print(
            "qdrant_vector_compare=PASS-LIVE active_hits=10 restored_hits=10 "
            f"exact_rank_match=true max_score_delta={score_delta:.8f} ids_sha256={result_digest}"
        )
        print(
            "qdrant_hybrid_rerank=PASS-LIVE "
            f"bm25_hits={len(trace.bm25_results)} vector_hits={len(trace.vector_results)} "
            f"rerank_applied=true rerank_model={trace.rerank_metadata.get('model')} "
            f"final_hits={len(trace.final_results)}"
        )
    finally:
        if runtime is not None:
            await runtime.close()
        await client.close()


async def delete_temporary(collection: str) -> None:
    _validate_temp_collection(collection)
    client = await _client()
    try:
        if await client.collection_exists(collection):
            await client.delete_collection(collection)
        for _ in range(60):
            if not await client.collection_exists(collection):
                break
            await asyncio.sleep(1)
        else:
            raise VerificationError("temporary_collection_delete_timeout")
        if not await client.collection_exists(ACTIVE_COLLECTION):
            raise VerificationError("active_collection_missing_after_cleanup")
        if not await client.collection_exists(ROLLBACK_COLLECTION):
            raise VerificationError("rollback_collection_missing_after_cleanup")
    finally:
        await client.close()
    print("qdrant_restore_cleanup=PASS-LIVE temporary_absent=true active=true rollback=true")


async def main() -> None:
    if len(sys.argv) != 3:
        raise VerificationError("usage_error")
    collection, action = sys.argv[1:]
    if action == "preflight":
        await preflight(collection)
    elif action == "verify":
        await verify(collection)
    elif action == "delete":
        await delete_temporary(collection)
    else:
        raise VerificationError("unknown_action")


try:
    asyncio.run(main())
except Exception as exc:  # noqa: BLE001 - suppress third-party response details.
    print(f"qdrant_restore_verify=FAIL error_type={type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1) from None
