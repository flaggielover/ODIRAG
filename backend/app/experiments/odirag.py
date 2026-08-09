from __future__ import annotations

import hashlib
import json
import math
import uuid
from collections.abc import Mapping
from typing import Any, cast

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.bm25 import BM25Document, BM25Index
from app.chunking import ChunkingConfig, HeadingAwareChunker
from app.config import Settings
from app.embedding import EmbeddingProvider, RemoteEmbeddingProvider
from app.evaluation import HALLUCINATION_SCOPE
from app.experiments.service import (
    EvaluationCaseResult,
    EvaluationOutcome,
    EvaluationRequest,
)
from app.models import Document
from app.rag import GroundingService
from app.repositories.chat import ChatRepository
from app.repositories.evaluation import EvaluationRepository
from app.rerank import (
    DeterministicRerankProvider,
    NoRerankProvider,
    RemoteRerankProvider,
    RerankProvider,
)
from app.retrieval import RetrievalConfig, RetrievalEngine
from app.router import QueryRouter
from app.runtime import ApplicationRuntime, resolve_runtime_path
from app.schemas.evaluation import EvaluationRunRequest
from app.services.chat import ChatService
from app.services.evaluation import EvaluationApplicationService
from app.vector_store import InMemoryVectorStore, VectorPoint


class ODIRAGVariantEvaluationRunner:
    """Apply one experiment variant to an isolated index and run the real benchmark."""

    def __init__(
        self,
        session: AsyncSession,
        settings: Settings,
        runtime: ApplicationRuntime,
        evaluation_request: EvaluationRunRequest,
        *,
        experiment_id: int,
    ) -> None:
        self.session = session
        self.settings = settings
        self.runtime = runtime
        self.evaluation_request = evaluation_request
        self.experiment_id = experiment_id

    async def run(self, request: EvaluationRequest) -> EvaluationOutcome:
        parameters = _parameters(request.parameters)
        engine, applied = await self._engine(parameters)
        prompt = str(parameters.get("prompt_text", self.runtime.grounded_answer_prompt))
        prompt_version = str(
            parameters.get(
                "prompt_version",
                self.runtime.grounded_answer_prompt_version,
            )
        )
        chat_service = ChatService(
            ChatRepository(self.session),
            QueryRouter(),
            engine,
            self.runtime.evidence_sufficiency_gate,
            GroundingService(
                minimum_hits=self.settings.grounding_minimum_hits,
                minimum_score=self.settings.grounding_minimum_score,
                require_official_source=self.settings.grounding_require_official_source,
                refuse_on_conflict=self.settings.grounding_refuse_on_conflict,
            ),
            orchestrator=self.runtime.llm_orchestrator,
            prompt=prompt,
            prompt_version=prompt_version,
        )
        run_request = self.evaluation_request.model_copy(
            update={
                "run_name": f"{request.experiment_name}-{request.role}-{request.variant_name}",
                "retrieval_version": f"experiment:{request.variant_name}",
                "prompt_version": prompt_version,
                "top_k": engine.config.final_top_k,
            }
        )
        service = EvaluationApplicationService(
            EvaluationRepository(self.session),
            chat_service,
            artifact_root=resolve_runtime_path(self.settings.evaluation_artifact_dir),
            embedding_model=engine.embedding_provider.model_name,
            rerank_model=engine.rerank_provider.model_name,
            default_retrieval_version=f"experiment:{request.variant_name}",
            default_prompt_version=prompt_version,
        )
        run = await service.run(
            run_request,
            experiment_id=self.experiment_id,
            run_metadata={
                "experiment_name": request.experiment_name,
                "experiment_role": request.role,
                "variant_name": request.variant_name,
                "requested_parameters": parameters,
                "applied_parameters": applied,
                "hallucination_scope": HALLUCINATION_SCOPE,
            },
            additional_filters=_mapping(parameters.get("metadata_filters", {})),
        )
        report = await service.report(run)
        aggregate = _mapping(report["aggregate"])
        questions = report.get("questions", [])
        if not isinstance(questions, list):
            raise ValueError("evaluation report questions must be a list")
        return EvaluationOutcome(
            metrics=_comparison_metrics(aggregate),
            cases=tuple(_case_result(item, run.id) for item in questions),
            metadata={
                "evaluation_run_id": run.id,
                "variant_name": request.variant_name,
                "applied_parameters": _json_value(applied),
                "artifacts": _json_value(report.get("artifacts", {})),
            },
        )

    async def _engine(
        self, parameters: dict[str, Any]
    ) -> tuple[RetrievalEngine, dict[str, JsonValue]]:
        _validate_parameter_names(parameters)
        chunker = _chunker(self.runtime.chunker, parameters)
        embedding = _embedding_provider(self.settings, self.runtime, parameters)
        rerank = _rerank_provider(self.settings, self.runtime, parameters)
        config = _retrieval_config(self.runtime.retrieval_config, parameters)
        documents = await self._documents()
        bm25 = BM25Index()
        vector_store = InMemoryVectorStore()
        bm25_documents: list[BM25Document] = []
        texts: list[str] = []
        point_metadata: list[tuple[str, str, str, str, dict[str, Any]]] = []
        variant_key = json.dumps(parameters, ensure_ascii=False, sort_keys=True)
        for document in documents:
            drafts = chunker.chunk(document.content)
            for index, draft in enumerate(drafts):
                point_id = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"experiment:{variant_key}:{document.document_id}:{index}:"
                        f"{hashlib.sha256(draft.content.encode('utf-8')).hexdigest()}",
                    )
                )
                metadata = _document_metadata(document, draft.section_path, draft.section_title)
                bm25_documents.append(
                    BM25Document(
                        chunk_id=point_id,
                        document_id=document.document_id,
                        title=document.title,
                        content=draft.content,
                        source_url=document.source_url,
                        metadata=metadata,
                    )
                )
                texts.append(draft.content)
                point_metadata.append(
                    (
                        point_id,
                        document.document_id,
                        document.title,
                        document.source_url,
                        metadata,
                    )
                )
        if not texts:
            raise ValueError("the experiment corpus has no approved document chunks")
        vectors = await embedding.embed_documents(texts)
        if len(vectors) != len(texts):
            raise ValueError("embedding provider returned the wrong vector count")
        dimensions = len(vectors[0])
        if dimensions <= 0 or any(len(vector) != dimensions for vector in vectors):
            raise ValueError("embedding provider returned inconsistent vector dimensions")
        await vector_store.ensure_collection(dimensions)
        await vector_store.upsert(
            [
                VectorPoint(
                    point_id=identity[0],
                    vector=list(vector),
                    document_id=identity[1],
                    content=text,
                    title=identity[2],
                    source_url=identity[3],
                    payload=identity[4],
                )
                for identity, text, vector in zip(point_metadata, texts, vectors, strict=True)
            ]
        )
        bm25.rebuild(bm25_documents)
        applied: dict[str, JsonValue] = {
            "chunking": {
                "target_chars": chunker.config.target_chars,
                "min_chars": chunker.config.min_chars,
                "max_chars": chunker.config.max_chars,
                "overlap_chars": chunker.config.overlap_chars,
            },
            "embedding_model": embedding.model_name,
            "retrieval": {
                "bm25_top_k": config.bm25_top_k,
                "vector_top_k": config.vector_top_k,
                "rrf_k": config.rrf_k,
                "rerank_top_k": config.rerank_top_k,
                "final_top_k": config.final_top_k,
                "score_threshold": config.score_threshold,
            },
            "rerank_model": rerank.model_name,
            "metadata_filters": _json_value(parameters.get("metadata_filters", {})),
            "prompt_version": str(
                parameters.get("prompt_version", self.runtime.grounded_answer_prompt_version)
            ),
            "corpus_document_count": len(documents),
            "corpus_chunk_count": len(texts),
        }
        return (
            RetrievalEngine(
                bm25_index=bm25,
                embedding_provider=embedding,
                vector_store=vector_store,
                rerank_provider=rerank,
                config=config,
            ),
            applied,
        )

    async def _documents(self) -> list[Document]:
        result = await self.session.execute(
            select(Document)
            .where(Document.final_status == "approved")
            .options(selectinload(Document.source))
            .order_by(Document.document_id)
        )
        return list(result.scalars())


class _NamedDeterministicEmbeddingProvider:
    provider_name = "deterministic-experiment"

    def __init__(self, model_name: str, dimensions: int) -> None:
        self.model_name = model_name
        self.dimensions = dimensions

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        seed = hashlib.sha256(f"{self.model_name}\0{text}".encode()).digest()
        values = [
            ((seed[index % len(seed)] / 255.0) * 2.0) - 1.0 for index in range(self.dimensions)
        ]
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]


def _chunker(base: HeadingAwareChunker, parameters: dict[str, Any]) -> HeadingAwareChunker:
    raw = _mapping(parameters.get("chunking", {}))
    aliases = {
        "chunk_size": "target_chars",
        "overlap": "overlap_chars",
        "overlap_chars": "overlap_chars",
    }
    for source, target in aliases.items():
        if source in parameters:
            raw[target] = parameters[source]
    allowed = {"target_chars", "min_chars", "max_chars", "overlap_chars"}
    unknown = set(raw) - allowed
    if unknown:
        raise ValueError(f"unsupported chunking parameters: {sorted(unknown)}")
    values = {
        "target_chars": base.config.target_chars,
        "min_chars": base.config.min_chars,
        "max_chars": base.config.max_chars,
        "overlap_chars": base.config.overlap_chars,
        **{key: int(value) for key, value in raw.items()},
    }
    return HeadingAwareChunker(ChunkingConfig(**values))


def _embedding_provider(
    settings: Settings,
    runtime: ApplicationRuntime,
    parameters: dict[str, Any],
) -> EmbeddingProvider:
    requested = str(parameters.get("embedding_model", runtime.embedding_provider.model_name))
    dimensions = int(parameters.get("embedding_dimensions", settings.embedding_dimensions))
    if requested == runtime.embedding_provider.model_name:
        return runtime.embedding_provider
    if settings.embedding_provider == "deterministic":
        return _NamedDeterministicEmbeddingProvider(requested, dimensions)
    return RemoteEmbeddingProvider(
        base_url=settings.embedding_base_url,
        api_key=(
            settings.embedding_api_key.get_secret_value() if settings.embedding_api_key else None
        ),
        model_name=requested,
        dimensions=dimensions,
        timeout_seconds=settings.dependency_timeout_seconds,
    )


def _rerank_provider(
    settings: Settings,
    runtime: ApplicationRuntime,
    parameters: dict[str, Any],
) -> RerankProvider:
    requested = parameters.get("rerank", parameters.get("rerank_model"))
    if requested is None or requested is True:
        return runtime.rerank_provider
    if requested is False or str(requested).lower() in {"none", "disabled", "false"}:
        return NoRerankProvider()
    if str(requested).lower() in {"deterministic", "local"}:
        return DeterministicRerankProvider()
    model_name = str(requested)
    if model_name == runtime.rerank_provider.model_name:
        return runtime.rerank_provider
    if settings.rerank_provider != "remote":
        raise ValueError(f"rerank model {model_name!r} requires the remote rerank provider")
    return RemoteRerankProvider(
        base_url=settings.rerank_base_url,
        api_key=(settings.rerank_api_key.get_secret_value() if settings.rerank_api_key else None),
        model_name=model_name,
        timeout_seconds=settings.dependency_timeout_seconds,
    )


def _retrieval_config(base: RetrievalConfig, parameters: dict[str, Any]) -> RetrievalConfig:
    raw = _mapping(parameters.get("retrieval", {}))
    aliases = {
        "bm25_top_k": "bm25_top_k",
        "vector_top_k": "vector_top_k",
        "rrf_k": "rrf_k",
        "rerank_top_k": "rerank_top_k",
        "final_top_k": "final_top_k",
        "score_threshold": "score_threshold",
    }
    for source, target in aliases.items():
        if source in parameters:
            raw[target] = parameters[source]
    if "top_k" in parameters:
        top_k = int(parameters["top_k"])
        raw.update(
            bm25_top_k=top_k,
            vector_top_k=top_k,
            final_top_k=top_k,
        )
    unknown = set(raw) - set(aliases.values())
    if unknown:
        raise ValueError(f"unsupported retrieval parameters: {sorted(unknown)}")
    updates: dict[str, int | float] = {}
    for key, value in raw.items():
        updates[key] = float(value) if key == "score_threshold" else int(value)
    return RetrievalConfig(
        bm25_top_k=int(updates.get("bm25_top_k", base.bm25_top_k)),
        vector_top_k=int(updates.get("vector_top_k", base.vector_top_k)),
        rrf_k=int(updates.get("rrf_k", base.rrf_k)),
        rerank_top_k=int(updates.get("rerank_top_k", base.rerank_top_k)),
        final_top_k=int(updates.get("final_top_k", base.final_top_k)),
        score_threshold=float(updates.get("score_threshold", base.score_threshold)),
    )


def _document_metadata(
    document: Document,
    section_path: tuple[str, ...],
    section_title: str | None,
) -> dict[str, Any]:
    values: dict[str, Any] = {
        "source_id": document.source_id,
        "source_name": document.source.name if document.source is not None else None,
        "official_status": (
            document.source.official_status if document.source is not None else None
        ),
        "region": document.region,
        "city": document.city,
        "document_type": document.document_type,
        "issuing_authority": document.issuing_authority,
        "document_number": document.document_number,
        "publish_date": (document.publish_date.isoformat() if document.publish_date else None),
        "document_version": document.version,
        "section_path": " > ".join(section_path) or None,
        "section_title": section_title,
    }
    return {key: value for key, value in values.items() if value is not None}


def _comparison_metrics(aggregate: Mapping[str, Any]) -> dict[str, float]:
    names = (
        "recall_at_1",
        "recall_at_5",
        "recall_at_10",
        "mrr",
        "ndcg_at_10",
        "document_hit_rate",
        "chunk_hit_rate",
        "answer_point_coverage",
        "citation_accuracy",
        "citation_completeness",
        "refusal_accuracy",
        "hallucination_rate",
        "p50_latency_ms",
        "p95_latency_ms",
        "average_tokens",
        "average_cost",
    )
    return {name: float(aggregate[name]) for name in names}


def _case_result(payload: object, evaluation_run_id: int) -> EvaluationCaseResult:
    item = _mapping(payload)
    metrics = _mapping(item.get("metrics", {}))
    failures: list[str] = []
    if item.get("error"):
        failures.append(str(item["error"]))
    checks = {
        "document_hit": bool(item.get("expected_document_ids")),
        "chunk_hit": bool(item.get("expected_chunk_ids")),
        "answer_point_coverage": bool(item.get("expected_answer_points")),
        "citation_accuracy": bool(item.get("expected_chunk_ids"))
        and not bool(item.get("should_refuse")),
        "citation_completeness": bool(item.get("expected_chunk_ids"))
        and not bool(item.get("should_refuse")),
        "refusal_correct": True,
    }
    for name, required in checks.items():
        if required and float(metrics.get(name, 0.0)) < 1.0:
            failures.append(name)
    if float(metrics.get("hallucination_rate", 0.0)) > 0:
        failures.append("hallucination_rate")
    return EvaluationCaseResult(
        case_id=str(item.get("question_id", "unknown")),
        passed=not failures,
        failure_reason=", ".join(failures) if failures else None,
        details={
            "evaluation_run_id": evaluation_run_id,
            "metrics": _json_value(metrics),
            "retrieved_document_ids": _json_value(item.get("retrieved_document_ids", [])),
            "retrieved_chunk_ids": _json_value(item.get("retrieved_chunk_ids", [])),
        },
    )


def _validate_parameter_names(parameters: dict[str, Any]) -> None:
    allowed = {
        "chunking",
        "chunk_size",
        "overlap",
        "overlap_chars",
        "embedding_model",
        "embedding_dimensions",
        "retrieval",
        "top_k",
        "bm25_top_k",
        "vector_top_k",
        "rrf_k",
        "rerank",
        "rerank_model",
        "rerank_top_k",
        "final_top_k",
        "score_threshold",
        "metadata_filters",
        "prompt_version",
        "prompt_text",
    }
    unknown = set(parameters) - allowed
    if unknown:
        raise ValueError(f"unsupported experiment parameters: {sorted(unknown)}")


def _parameters(value: Mapping[str, JsonValue]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


def _mapping(value: object) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected a mapping")
    return {str(key): item for key, item in value.items()}


def _json_value(value: object) -> JsonValue:
    return cast(JsonValue, json.loads(json.dumps(value, ensure_ascii=False, default=str)))
