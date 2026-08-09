from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from app.bm25 import BM25Index
from app.cache import (
    EmbeddingCache,
    InMemoryEmbeddingCache,
    RedisEmbeddingCache,
)
from app.chunking import HeadingAwareChunker, load_chunking_config
from app.config import Settings
from app.embedding import (
    DeterministicEmbeddingProvider,
    EmbeddingBatcher,
    EmbeddingProvider,
    RemoteEmbeddingProvider,
)
from app.llm import CozeAdapter, DirectLLMAdapter, LLMOrchestrator
from app.rag import EvidenceSufficiencyGate
from app.rerank import (
    DeterministicRerankProvider,
    NoRerankProvider,
    RemoteRerankProvider,
    RerankProvider,
)
from app.retrieval import RetrievalConfig, RetrievalEngine
from app.vector_store import InMemoryVectorStore, QdrantVectorStore, VectorStore

logger = structlog.get_logger(__name__)
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class ApplicationRuntime:
    chunker: HeadingAwareChunker
    embedding_provider: EmbeddingProvider
    embedding_cache: EmbeddingCache
    embedding_batcher: EmbeddingBatcher
    vector_store: VectorStore
    rerank_provider: RerankProvider
    evidence_sufficiency_gate: EvidenceSufficiencyGate
    llm_orchestrator: LLMOrchestrator | None
    grounded_answer_prompt: str
    grounded_answer_prompt_version: str
    bm25_index: BM25Index
    bm25_snapshot_path: Path
    retrieval_config: RetrievalConfig

    def retrieval_engine(self) -> RetrievalEngine:
        return RetrievalEngine(
            bm25_index=self.bm25_index,
            embedding_provider=self.embedding_provider,
            vector_store=self.vector_store,
            rerank_provider=self.rerank_provider,
            config=self.retrieval_config,
        )


def build_application_runtime(settings: Settings) -> ApplicationRuntime:
    chunking_path = resolve_runtime_path(settings.chunking_config_path)
    snapshot_path = resolve_runtime_path(settings.bm25_snapshot_path)
    grounded_prompt_path = resolve_runtime_path(settings.grounded_answer_prompt_path)
    embedding_provider = _embedding_provider(settings)
    embedding_cache = _embedding_cache(settings)
    batcher = EmbeddingBatcher(
        embedding_provider,
        embedding_cache,
        batch_size=settings.embedding_batch_size,
        minimum_interval_seconds=settings.embedding_minimum_interval_seconds,
        cost_per_1k_chars=settings.embedding_cost_per_1k_chars,
        version=settings.embedding_version,
    )
    return ApplicationRuntime(
        chunker=HeadingAwareChunker(load_chunking_config(chunking_path)),
        embedding_provider=embedding_provider,
        embedding_cache=embedding_cache,
        embedding_batcher=batcher,
        vector_store=_vector_store(settings),
        rerank_provider=_rerank_provider(settings),
        evidence_sufficiency_gate=EvidenceSufficiencyGate(
            minimum_confidence=settings.evidence_sufficiency_minimum_confidence,
            minimum_hit_contribution=(settings.evidence_sufficiency_minimum_hit_contribution),
            minimum_answer_overlap=(settings.evidence_sufficiency_minimum_answer_overlap),
        ),
        llm_orchestrator=_llm_orchestrator(settings),
        grounded_answer_prompt=grounded_prompt_path.read_text(encoding="utf-8"),
        grounded_answer_prompt_version=settings.grounded_answer_prompt_version,
        bm25_index=_load_bm25(snapshot_path),
        bm25_snapshot_path=snapshot_path,
        retrieval_config=RetrievalConfig(
            bm25_top_k=settings.retrieval_bm25_top_k,
            vector_top_k=settings.retrieval_vector_top_k,
            rrf_k=settings.retrieval_rrf_k,
            rerank_top_k=settings.retrieval_rerank_top_k,
            final_top_k=settings.retrieval_final_top_k,
            score_threshold=settings.retrieval_score_threshold,
        ),
    )


def resolve_runtime_path(path: Path) -> Path:
    return path if path.is_absolute() else (_BACKEND_ROOT / path).resolve()


def _embedding_provider(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "deterministic":
        return DeterministicEmbeddingProvider(settings.embedding_dimensions)
    return RemoteEmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=(
            settings.embedding_api_key.get_secret_value() if settings.embedding_api_key else None
        ),
        model_name=settings.embedding_model,
        dimensions=settings.embedding_dimensions,
        timeout_seconds=settings.dependency_timeout_seconds,
    )


def _embedding_cache(settings: Settings) -> EmbeddingCache:
    if settings.embedding_cache_provider == "memory":
        return InMemoryEmbeddingCache()
    return RedisEmbeddingCache(
        settings.redis_url,
        ttl_seconds=settings.embedding_cache_ttl_seconds,
    )


def _vector_store(settings: Settings) -> VectorStore:
    if settings.vector_store_provider == "memory":
        return InMemoryVectorStore()
    return QdrantVectorStore(
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection,
        api_key=(settings.qdrant_api_key.get_secret_value() if settings.qdrant_api_key else None),
    )


def _rerank_provider(settings: Settings) -> RerankProvider:
    if settings.rerank_provider == "deterministic":
        return DeterministicRerankProvider()
    if settings.rerank_provider == "remote":
        return RemoteRerankProvider(
            base_url=settings.rerank_base_url,
            api_key=(
                settings.rerank_api_key.get_secret_value() if settings.rerank_api_key else None
            ),
            model_name=settings.rerank_model,
            timeout_seconds=settings.dependency_timeout_seconds,
        )
    return NoRerankProvider()


def _llm_orchestrator(settings: Settings) -> LLMOrchestrator | None:
    if settings.answer_provider == "extractive":
        return None
    if settings.llm_provider == "coze":
        return CozeAdapter(
            base_url=settings.coze_base_url,
            api_token=(
                settings.coze_api_token.get_secret_value() if settings.coze_api_token else None
            ),
            bot_id=settings.coze_bot_id,
            timeout_seconds=settings.dependency_timeout_seconds,
        )
    return DirectLLMAdapter(
        base_url=settings.direct_llm_base_url,
        api_key=(
            settings.direct_llm_api_key.get_secret_value() if settings.direct_llm_api_key else None
        ),
        model_name=settings.direct_llm_model,
        timeout_seconds=settings.dependency_timeout_seconds,
    )


def _load_bm25(path: Path) -> BM25Index:
    if not path.is_file():
        return BM25Index()
    try:
        return BM25Index.load(path)
    except (OSError, ValueError) as exc:
        logger.warning("bm25_snapshot_unavailable", path=str(path), error=str(exc))
        return BM25Index()
