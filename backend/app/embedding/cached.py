from __future__ import annotations

import asyncio
import hashlib
import math
from functools import partial

import structlog

from app.cache import EmbeddingCache
from app.embedding.providers import EmbeddingProvider

logger = structlog.get_logger(__name__)


class CachedQueryEmbeddingProvider:
    """Cache query vectors without making retrieval depend on cache availability."""

    def __init__(
        self,
        provider: EmbeddingProvider,
        cache: EmbeddingCache,
        *,
        version: str,
    ) -> None:
        self.provider = provider
        self.cache = cache
        self.version = version
        self.provider_name = provider.provider_name
        self.model_name = provider.model_name
        endpoint = str(getattr(provider, "base_url", "local"))
        self.endpoint_fingerprint = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16]
        self._inflight: dict[str, asyncio.Task[list[float]]] = {}
        self._inflight_lock = asyncio.Lock()
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self.provider.embed_documents(texts)

    async def embed_query(self, text: str) -> list[float]:
        key = self._key(text)
        async with self._inflight_lock:
            task = self._inflight.get(key)
            if task is None:
                task = asyncio.create_task(self._load_or_embed(key, text))
                self._inflight[key] = task
                task.add_done_callback(partial(self._schedule_clear, key))
        return list(await asyncio.shield(task))

    def _schedule_clear(
        self,
        key: str,
        task: asyncio.Future[list[float]],
    ) -> None:
        cleanup = asyncio.create_task(self._clear_inflight(key, task))
        self._cleanup_tasks.add(cleanup)
        cleanup.add_done_callback(self._cleanup_tasks.discard)

    async def _clear_inflight(
        self,
        key: str,
        task: asyncio.Future[list[float]],
    ) -> None:
        async with self._inflight_lock:
            if self._inflight.get(key) is task:
                self._inflight.pop(key, None)

    async def _load_or_embed(self, key: str, text: str) -> list[float]:
        cached: list[float] | None = None
        try:
            cached = await self.cache.get(key)
        except Exception as exc:
            logger.warning(
                "query_embedding_cache_read_failed",
                error_type=exc.__class__.__name__,
            )
        if cached is not None and self._valid(cached):
            return list(cached)

        vector = await self.provider.embed_query(text)
        try:
            await self.cache.set(key, vector)
        except Exception as exc:
            logger.warning(
                "query_embedding_cache_write_failed",
                error_type=exc.__class__.__name__,
            )
        return vector

    def _key(self, normalized_query: str) -> str:
        digest = hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()
        return (
            f"query-embedding:{self.provider_name}:{self.model_name}:"
            f"{self.endpoint_fingerprint}:{self.version}:{digest}"
        )

    def _valid(self, vector: list[float]) -> bool:
        if not vector or not all(math.isfinite(value) for value in vector):
            return False
        expected = getattr(self.provider, "dimensions", None)
        return not isinstance(expected, int) or expected <= 0 or len(vector) == expected
