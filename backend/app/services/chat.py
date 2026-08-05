from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from decimal import Decimal
from time import perf_counter
from typing import Any

from app.llm import LLMOrchestrator
from app.models import QueryTrace
from app.providers import ProviderResponseError
from app.rag import Citation, EvidenceDecision, GroundingService
from app.repositories.chat import ChatRepository
from app.retrieval import RetrievalEngine, RetrievalHit, RetrievalMode, RetrievalTrace
from app.router import QueryRouter, QueryType


@dataclass(frozen=True, slots=True)
class ChatAnswer:
    trace_id: str
    query_type: QueryType
    answer: str
    refusal: bool
    refusal_reasons: tuple[str, ...]
    conflicts: tuple[str, ...]
    outdated: tuple[str, ...]
    citations: tuple[Citation, ...]
    filters: dict[str, Any]
    structured_count: int | None
    retrieval_trace: RetrievalTrace | None
    token_usage_json: dict[str, Any]
    cost: Decimal


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        router: QueryRouter,
        retrieval_engine: RetrievalEngine,
        grounding: GroundingService,
        *,
        orchestrator: LLMOrchestrator | None = None,
        prompt: str = "",
        prompt_version: str = "v1",
    ) -> None:
        self.repository = repository
        self.router = router
        self.retrieval_engine = retrieval_engine
        self.grounding = grounding
        self.orchestrator = orchestrator
        self.prompt = prompt
        self.prompt_version = prompt_version

    async def answer(
        self, query: str, *, explicit_filters: dict[str, Any] | None = None
    ) -> ChatAnswer:
        started = perf_counter()
        route = self.router.analyze(query, explicit_filters)
        structured_count: int | None = None
        retrieval_trace: RetrievalTrace | None = None
        decision = EvidenceDecision(True, (), (), (), ())
        token_usage_json: dict[str, Any] = {
            "measurement": "not_available",
            "cost_measurement": "not_available",
        }
        cost = Decimal("0")
        if route.query_type in {QueryType.SQL, QueryType.COMPOSITE}:
            structured_count = await self.repository.count_approved_documents(route.filters)
        if route.query_type is QueryType.SQL:
            trace_id = str(uuid.uuid4())
            answer = f"数据库中符合条件且已审核通过的政策文档共 {structured_count} 份。"
            refusal = False
            refusal_reasons: tuple[str, ...] = ()
            citations: tuple[Citation, ...] = ()
        else:
            retrieval_trace = await self.retrieval_engine.search(
                query,
                mode=RetrievalMode.HYBRID_RERANK,
                filters=route.filters,
            )
            trace_id = retrieval_trace.trace_id
            decision = self.grounding.assess(query, list(retrieval_trace.final_results))
            if not decision.sufficient:
                answer = self._refusal_text(decision)
                refusal = True
                refusal_reasons = decision.reasons
                citations = decision.citations
            else:
                (
                    answer,
                    citations,
                    refusal,
                    refusal_reasons,
                    token_usage_json,
                    cost,
                ) = await self._grounded_answer(
                    query,
                    retrieval_trace,
                    decision,
                )
                if route.query_type is QueryType.COMPOSITE and not refusal:
                    answer = f"在符合筛选条件的 {structured_count} 份文档中，{answer}"
        result = ChatAnswer(
            trace_id=trace_id,
            query_type=route.query_type,
            answer=answer,
            refusal=refusal,
            refusal_reasons=refusal_reasons,
            conflicts=decision.conflicts,
            outdated=decision.outdated,
            citations=citations,
            filters=route.filters,
            structured_count=structured_count,
            retrieval_trace=retrieval_trace,
            token_usage_json=token_usage_json,
            cost=cost,
        )
        await self._persist(result, query, started)
        return result

    async def get_trace(self, trace_id: str) -> QueryTrace | None:
        return await self.repository.get_trace(trace_id)

    async def list_traces(
        self,
        *,
        limit: int,
        query_type: str | None = None,
        refusal: bool | None = None,
    ) -> list[QueryTrace]:
        return await self.repository.list_traces(
            limit=limit,
            query_type=query_type,
            refusal=refusal,
        )

    async def _grounded_answer(
        self,
        query: str,
        trace: RetrievalTrace,
        decision: EvidenceDecision,
    ) -> tuple[str, tuple[Citation, ...], bool, tuple[str, ...], dict[str, Any], Decimal]:
        if self.orchestrator is None:
            selected = decision.citations[:3]
            lines = [
                f"{index}. {citation.quote}（来源：《{citation.title}》）"
                for index, citation in enumerate(selected, start=1)
            ]
            return (
                "根据检索到的官方文件：" + " ".join(lines),
                selected,
                False,
                (),
                {"measurement": "not_available", "cost_measurement": "not_applicable"},
                Decimal("0"),
            )
        citation_by_chunk = {citation.chunk_id: citation for citation in decision.citations}
        eligible_hits = [hit for hit in trace.final_results if hit.chunk_id in citation_by_chunk]
        generated = await self.orchestrator.generate_answer(
            query=query,
            context=[_hit_payload(hit) for hit in eligible_hits],
            prompt=self.prompt,
        )
        if generated.refusal:
            reason = generated.refusal_reason or "model_refusal"
            return generated.answer, (), True, (reason,), *_result_usage(generated)
        cited_ids = tuple(dict.fromkeys(generated.cited_chunk_ids))
        if not cited_ids or any(chunk_id not in citation_by_chunk for chunk_id in cited_ids):
            raise ProviderResponseError("grounded_answer", "citations are missing or invalid")
        citations = tuple(citation_by_chunk[chunk_id] for chunk_id in cited_ids)
        allowed_urls = {citation.url for citation in citations}
        generated_urls = set(re.findall(r"https?://[^\s)\]}>]+", generated.answer))
        if not generated_urls.issubset(allowed_urls):
            raise ProviderResponseError("grounded_answer", "answer contains an unknown URL")
        usage, cost = _result_usage(generated)
        return generated.answer, citations, False, (), usage, cost

    async def _persist(self, result: ChatAnswer, query: str, started: float) -> None:
        retrieval = result.retrieval_trace
        await self.repository.add_trace(
            QueryTrace(
                trace_id=result.trace_id,
                user_query=query,
                query_type=result.query_type.value,
                parsed_filters_json=result.filters,
                bm25_results_json=_hits_payload(retrieval.bm25_results if retrieval else ()),
                vector_results_json=_hits_payload(retrieval.vector_results if retrieval else ()),
                fusion_results_json=_hits_payload(retrieval.fusion_results if retrieval else ()),
                rerank_results_json=_hits_payload(retrieval.rerank_results if retrieval else ()),
                final_context_json=_hits_payload(retrieval.final_results if retrieval else ()),
                prompt_version=self.prompt_version,
                prompt_snapshot_json={
                    "version": self.prompt_version,
                    "content": self.prompt,
                    "mode": "llm" if self.orchestrator is not None else "extractive",
                },
                model_name=(
                    self.orchestrator.model_name
                    if self.orchestrator is not None
                    else "extractive-grounded-v1"
                ),
                answer=result.answer,
                citations_json=[_citation_payload(citation) for citation in result.citations],
                refusal=result.refusal,
                latency_ms=round((perf_counter() - started) * 1000),
                token_usage_json=result.token_usage_json,
                cost=result.cost,
            )
        )
        await self.repository.commit()

    @staticmethod
    def _refusal_text(decision: EvidenceDecision) -> str:
        reasons = ", ".join(decision.reasons) or "evidence_not_sufficient"
        return f"无法基于当前已验证证据可靠回答。原因：{reasons}。"


def _hit_payload(hit: RetrievalHit) -> dict[str, Any]:
    return {
        "chunk_id": hit.chunk_id,
        "document_id": hit.document_id,
        "title": hit.title,
        "content": hit.content,
        "source_url": hit.source_url,
        "score": hit.score,
        "rank": hit.rank,
        "metadata": hit.metadata,
    }


def _hits_payload(hits: tuple[RetrievalHit, ...]) -> list[dict[str, Any]]:
    return [_hit_payload(hit) for hit in hits]


def _citation_payload(citation: Citation) -> dict[str, Any]:
    return {
        "document_id": citation.document_id,
        "chunk_id": citation.chunk_id,
        "title": citation.title,
        "source": citation.source,
        "publication_date": citation.publication_date,
        "url": citation.url,
        "page": citation.page,
        "quote": citation.quote,
    }


def _result_usage(result: Any) -> tuple[dict[str, Any], Decimal]:
    usage = dict(getattr(result, "token_usage", {}) or {})
    cost = getattr(result, "cost", None)
    if not usage:
        usage["measurement"] = "not_available"
    if cost is None:
        usage.setdefault("cost_measurement", "not_available")
        return usage, Decimal("0")
    usage.setdefault("cost_measurement", "provider_reported")
    return usage, Decimal(str(cost))
