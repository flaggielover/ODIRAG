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
from app.rag import (
    Citation,
    EvidenceDecision,
    EvidenceSufficiencyDecision,
    EvidenceSufficiencyGate,
    GroundingService,
)
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
    evidence_sufficiency: EvidenceSufficiencyDecision | None
    evidence_gate_latency_ms: float
    answer_support_validated: bool | None


class ChatService:
    def __init__(
        self,
        repository: ChatRepository,
        router: QueryRouter,
        retrieval_engine: RetrievalEngine,
        evidence_gate: EvidenceSufficiencyGate,
        grounding: GroundingService,
        *,
        orchestrator: LLMOrchestrator | None = None,
        prompt: str = "",
        prompt_version: str = "v1",
    ) -> None:
        self.repository = repository
        self.router = router
        self.retrieval_engine = retrieval_engine
        self.evidence_gate = evidence_gate
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
        evidence_sufficiency: EvidenceSufficiencyDecision | None = None
        evidence_gate_latency_ms = 0.0
        answer_support_validated: bool | None = None
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
            gate_started = perf_counter()
            evidence_sufficiency = self.evidence_gate.assess(
                query,
                retrieval_trace.final_results,
            )
            evidence_gate_latency_ms = (perf_counter() - gate_started) * 1000
            self._validate_evidence_decision(
                evidence_sufficiency,
                retrieval_trace.final_results,
            )
            if not evidence_sufficiency.sufficient:
                answer = self._refusal_text((evidence_sufficiency.reason,))
                refusal = True
                refusal_reasons = (evidence_sufficiency.reason,)
                citations = ()
            else:
                supported_ids = set(evidence_sufficiency.supported_chunk_ids)
                supported_hits = [
                    hit for hit in retrieval_trace.final_results if hit.chunk_id in supported_ids
                ]
                decision = self.grounding.assess(query, supported_hits)
                if not decision.sufficient:
                    answer = self._refusal_text(decision.reasons)
                    refusal = True
                    refusal_reasons = decision.reasons
                    citations = ()
                else:
                    (
                        answer,
                        citations,
                        refusal,
                        refusal_reasons,
                        token_usage_json,
                        cost,
                        answer_support_validated,
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
            evidence_sufficiency=evidence_sufficiency,
            evidence_gate_latency_ms=evidence_gate_latency_ms,
            answer_support_validated=answer_support_validated,
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
    ) -> tuple[
        str,
        tuple[Citation, ...],
        bool,
        tuple[str, ...],
        dict[str, Any],
        Decimal,
        bool | None,
    ]:
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
                True,
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
            return (
                generated.answer,
                (),
                True,
                (reason,),
                *_result_usage(generated),
                None,
            )
        cited_ids = tuple(dict.fromkeys(generated.cited_chunk_ids))
        if not cited_ids or any(chunk_id not in citation_by_chunk for chunk_id in cited_ids):
            raise ProviderResponseError("grounded_answer", "citations are missing or invalid")
        citations = tuple(citation_by_chunk[chunk_id] for chunk_id in cited_ids)
        allowed_urls = {citation.url for citation in citations}
        generated_urls = set(re.findall(r"https?://[^\s)\]}>]+", generated.answer))
        if not generated_urls.issubset(allowed_urls):
            raise ProviderResponseError("grounded_answer", "answer contains an unknown URL")
        usage, cost = _result_usage(generated)
        cited_id_set = set(cited_ids)
        cited_hits = [hit for hit in trace.final_results if hit.chunk_id in cited_id_set]
        answer_support = self.evidence_gate.validate_answer(
            query=query,
            answer=generated.answer,
            cited_hits=cited_hits,
        )
        if not answer_support.sufficient:
            return (
                self._refusal_text((answer_support.reason,)),
                (),
                True,
                (answer_support.reason,),
                usage,
                cost,
                False,
            )
        return generated.answer, citations, False, (), usage, cost, True

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
                evidence_decision_json=self._evidence_payload(result),
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
    def _refusal_text(reasons: tuple[str, ...]) -> str:
        reason_text = ", ".join(reasons) or "evidence_not_sufficient"
        return f"无法基于当前已验证证据可靠回答。原因：{reason_text}。"

    @staticmethod
    def _validate_evidence_decision(
        decision: EvidenceSufficiencyDecision,
        final_hits: tuple[RetrievalHit, ...],
    ) -> None:
        if not 0 <= decision.confidence <= 1:
            raise ProviderResponseError("evidence_gate", "confidence is outside [0, 1]")
        supported_ids = decision.supported_chunk_ids
        if len(supported_ids) != len(set(supported_ids)):
            raise ProviderResponseError("evidence_gate", "supported chunk IDs are duplicated")
        final_ids = {hit.chunk_id for hit in final_hits}
        if any(chunk_id not in final_ids for chunk_id in supported_ids):
            raise ProviderResponseError("evidence_gate", "supported chunk ID is not a final hit")
        if decision.sufficient and (not supported_ids or decision.unsupported_aspects):
            raise ProviderResponseError("evidence_gate", "sufficient decision is inconsistent")
        if not decision.sufficient and supported_ids:
            raise ProviderResponseError("evidence_gate", "insufficient decision contains support")

    def _evidence_payload(self, result: ChatAnswer) -> dict[str, Any]:
        decision = result.evidence_sufficiency
        if decision is None:
            return {}
        retrieval = result.retrieval_trace
        payload = decision.as_dict()
        payload.update(
            {
                "status": "passed" if decision.sufficient else "insufficient",
                "candidate_count": (len(retrieval.final_results) if retrieval is not None else 0),
                "supported_count": len(decision.supported_chunk_ids),
                "latency_ms": round(result.evidence_gate_latency_ms, 3),
                "provider": self.evidence_gate.provider_name,
                "model": self.evidence_gate.model_name,
                "answer_support_validated": result.answer_support_validated,
                "refusal_reasons": list(result.refusal_reasons),
            }
        )
        return payload


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
