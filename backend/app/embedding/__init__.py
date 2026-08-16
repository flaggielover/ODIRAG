"""Embedding provider contracts and adapters."""

from app.embedding.batcher import EmbeddingBatcher, EmbeddingBatchResult
from app.embedding.cached import CachedQueryEmbeddingProvider
from app.embedding.providers import (
    DeterministicEmbeddingProvider,
    EmbeddingProvider,
    RemoteEmbeddingProvider,
)

__all__ = [
    "CachedQueryEmbeddingProvider",
    "DeterministicEmbeddingProvider",
    "EmbeddingBatchResult",
    "EmbeddingBatcher",
    "EmbeddingProvider",
    "RemoteEmbeddingProvider",
]
