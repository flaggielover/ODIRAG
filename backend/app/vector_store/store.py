from __future__ import annotations

import math
from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Protocol

from app.providers import ProviderResponseError, ProviderUnavailableError
from app.retrieval.models import RetrievalHit


@dataclass(frozen=True, slots=True)
class VectorPoint:
    point_id: str
    vector: list[float]
    document_id: str
    content: str
    title: str
    source_url: str
    payload: dict[str, Any] = field(default_factory=dict)


class VectorStore(Protocol):
    async def collection_exists(self) -> bool: ...

    async def ensure_collection(self, dimensions: int) -> None: ...

    async def upsert(self, points: list[VectorPoint]) -> None: ...

    async def delete(self, point_ids: list[str]) -> None: ...

    async def count(self, filters: dict[str, Any] | None = None) -> int: ...

    async def search(
        self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None
    ) -> list[RetrievalHit]: ...


class InMemoryVectorStore:
    """Deterministic vector store for tests and explicit demo mode."""

    def __init__(self) -> None:
        self._points: dict[str, VectorPoint] = {}
        self._dimensions: int | None = None

    @property
    def point_count(self) -> int:
        return len(self._points)

    @property
    def point_ids(self) -> frozenset[str]:
        return frozenset(self._points)

    async def collection_exists(self) -> bool:
        return self._dimensions is not None

    async def ensure_collection(self, dimensions: int) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        if self._dimensions is not None and self._dimensions != dimensions:
            raise ValueError("collection dimensions cannot change")
        self._dimensions = dimensions

    async def upsert(self, points: list[VectorPoint]) -> None:
        for point in points:
            if self._dimensions is None:
                self._dimensions = len(point.vector)
            if len(point.vector) != self._dimensions:
                raise ValueError("vector dimensions do not match the collection")
        self._points.update({point.point_id: point for point in points})

    async def delete(self, point_ids: list[str]) -> None:
        for point_id in point_ids:
            self._points.pop(point_id, None)

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        expected = filters or {}
        return sum(
            1
            for point in self._points.values()
            if _matches(
                {
                    **point.payload,
                    "document_id": point.document_id,
                    "content": point.content,
                    "title": point.title,
                    "source_url": point.source_url,
                },
                expected,
            )
        )

    async def search(
        self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None
    ) -> list[RetrievalHit]:
        candidates = []
        for point in self._points.values():
            payload = {
                **point.payload,
                "document_id": point.document_id,
                "content": point.content,
                "title": point.title,
                "source_url": point.source_url,
            }
            if _matches(payload, filters or {}):
                candidates.append((_cosine(vector, point.vector), point))
        candidates.sort(key=lambda item: (-item[0], item[1].point_id))
        return [
            RetrievalHit(
                point.point_id,
                point.document_id,
                point.content,
                point.title,
                point.source_url,
                score,
                rank,
                "vector",
                point.payload,
            )
            for rank, (score, point) in enumerate(candidates[:top_k], start=1)
        ]


class QdrantVectorStore:
    def __init__(self, *, url: str, collection_name: str, api_key: str | None = None) -> None:
        self.url = url
        self.collection_name = collection_name
        self.api_key = api_key

    def _client(self) -> Any:
        try:
            qdrant_client = import_module("qdrant_client")
        except ImportError as exc:
            raise ProviderUnavailableError("qdrant", "qdrant-client is not installed") from exc
        return qdrant_client.AsyncQdrantClient(url=self.url, api_key=self.api_key)

    async def collection_exists(self) -> bool:
        client = self._client()
        try:
            return bool(await client.collection_exists(self.collection_name))
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()

    async def ensure_collection(self, dimensions: int) -> None:
        models = import_module("qdrant_client.models")
        client = self._client()
        try:
            exists = await client.collection_exists(self.collection_name)
            if not exists:
                await client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=models.VectorParams(
                        size=dimensions,
                        distance=models.Distance.COSINE,
                    ),
                )
            else:
                info = await client.get_collection(self.collection_name)
                configured = _vector_dimensions(info.config.params.vectors)
                if configured is not None and configured != dimensions:
                    raise ProviderResponseError(
                        "qdrant",
                        f"collection dimension is {configured}, expected {dimensions}",
                    )
            info = await client.get_collection(self.collection_name)
            existing_indexes = set((info.payload_schema or {}).keys())
            for field_name, field_schema in _PAYLOAD_INDEXES:
                if field_name not in existing_indexes:
                    await client.create_payload_index(
                        collection_name=self.collection_name,
                        field_name=field_name,
                        field_schema=getattr(models.PayloadSchemaType, field_schema),
                        wait=True,
                    )
        except ProviderResponseError:
            raise
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()

    async def upsert(self, points: list[VectorPoint]) -> None:
        models = import_module("qdrant_client.models")
        client = self._client()
        try:
            await client.upsert(
                self.collection_name,
                points=[
                    models.PointStruct(
                        id=point.point_id,
                        vector=point.vector,
                        payload={
                            **point.payload,
                            "document_id": point.document_id,
                            "content": point.content,
                            "title": point.title,
                            "source_url": point.source_url,
                        },
                    )
                    for point in points
                ],
                wait=True,
            )
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()

    async def delete(self, point_ids: list[str]) -> None:
        models = import_module("qdrant_client.models")
        client = self._client()
        try:
            await client.delete(
                self.collection_name, models.PointIdsList(points=point_ids), wait=True
            )
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()

    async def count(self, filters: dict[str, Any] | None = None) -> int:
        models = import_module("qdrant_client.models")
        client = self._client()
        try:
            if not await client.collection_exists(self.collection_name):
                return 0
            response = await client.count(
                collection_name=self.collection_name,
                count_filter=_qdrant_filter(models, filters or {}),
                exact=True,
            )
            return int(response.count)
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()

    async def search(
        self, vector: list[float], top_k: int, filters: dict[str, Any] | None = None
    ) -> list[RetrievalHit]:
        models = import_module("qdrant_client.models")
        client = self._client()
        try:
            response = await client.query_points(
                collection_name=self.collection_name,
                query=vector,
                query_filter=_qdrant_filter(models, filters or {}),
                limit=top_k,
                with_payload=True,
            )
        except Exception as exc:
            raise ProviderUnavailableError("qdrant", str(exc)) from exc
        finally:
            await client.close()
        hits = []
        for rank, result in enumerate(response.points, start=1):
            payload = result.payload or {}
            hits.append(
                RetrievalHit(
                    str(result.id),
                    str(payload.get("document_id", "")),
                    str(payload.get("content", "")),
                    str(payload.get("title", "")),
                    str(payload.get("source_url", "")),
                    float(result.score),
                    rank,
                    "vector",
                    dict(payload),
                )
            )
        return hits


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have identical dimensions")
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if not left_norm or not right_norm:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (left_norm * right_norm)


def _matches(payload: dict[str, Any], filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if key.endswith("_gte"):
            if payload.get(key[:-4]) is None or str(payload[key[:-4]]) < str(expected):
                return False
        elif key.endswith("_lte"):
            if payload.get(key[:-4]) is None or str(payload[key[:-4]]) > str(expected):
                return False
        elif payload.get(key) != expected:
            return False
    return True


def _vector_dimensions(config: Any) -> int | None:
    if hasattr(config, "size"):
        return int(config.size)
    if isinstance(config, dict) and len(config) == 1:
        value = next(iter(config.values()))
        if hasattr(value, "size"):
            return int(value.size)
    return None


def _qdrant_filter(models: Any, filters: dict[str, Any]) -> Any | None:
    conditions = []
    ranges: dict[str, dict[str, Any]] = {}
    for key, expected in filters.items():
        if key.endswith(("_gte", "_lte")):
            field_name, bound = key.rsplit("_", 1)
            ranges.setdefault(field_name, {})[bound] = expected
        else:
            conditions.append(
                models.FieldCondition(key=key, match=models.MatchValue(value=expected))
            )
    for field_name, bounds in ranges.items():
        range_model = models.DatetimeRange if field_name == "publish_date" else models.Range
        conditions.append(models.FieldCondition(key=field_name, range=range_model(**bounds)))
    return models.Filter(must=conditions) if conditions else None


_PAYLOAD_INDEXES = (
    ("document_id", "KEYWORD"),
    ("source_id", "INTEGER"),
    ("region", "KEYWORD"),
    ("city", "KEYWORD"),
    ("document_type", "KEYWORD"),
    ("issuing_authority", "KEYWORD"),
    ("publish_date", "DATETIME"),
    ("document_version", "INTEGER"),
)
