from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from app.api.routes.chat import get_chat_service
from app.config import get_settings
from app.database import DatabaseManager
from app.models import QueryTrace
from app.repositories.chat import ChatRepository
from app.runtime import build_application_runtime
from sqlalchemy import func, select, text

SUPPORTED_QUERY = (
    "\u5b58\u91cfAPP\u5907\u6848\u9636\u6bb5\u662f\u4ec0\u4e48\u65f6\u95f4\uff1f"
    "\u5df2\u5b8c\u6210\u7f51\u7ad9\u5907\u6848\u624b\u7eed\u7684APP"
    "\u662f\u5426\u9700\u8981\u91cd\u590d\u586b\u62a5\u4e3b\u529e\u8005"
    "\u771f\u5b9e\u8eab\u4efd\u4fe1\u606f\uff1f"
)
OUT_OF_SCOPE_QUERY = (
    "\u706b\u661f\u5730\u8868\u662f\u5426\u5df2\u7ecf\u53d1\u73b0"
    "\u6d3b\u4f53\u6050\u9f99\uff1f"
)


class VerificationError(RuntimeError):
    pass


class NoWriteChatRepository(ChatRepository):
    def __init__(self, session: object) -> None:
        super().__init__(session)  # type: ignore[arg-type]
        self.traces: list[QueryTrace] = []

    async def add_trace(self, trace: QueryTrace) -> QueryTrace:
        self.traces.append(trace)
        return trace

    async def commit(self) -> None:
        return None


def _token_count(payload: dict[str, object]) -> int:
    total = payload.get("total_tokens")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return sum(
        value
        for value in (payload.get("prompt_tokens"), payload.get("completion_tokens"))
        if isinstance(value, int) and not isinstance(value, bool)
    )


async def main() -> None:
    settings = get_settings()
    if settings.embedding_model != "text-embedding-v4":
        raise VerificationError("unexpected_embedding_model")
    if settings.rerank_model != "rerank-v3.5":
        raise VerificationError("unexpected_rerank_model")
    if settings.llm_provider != "direct" or settings.answer_provider != "llm":
        raise VerificationError("unexpected_llm_configuration")

    runtime = build_application_runtime(settings)
    database = DatabaseManager(settings)
    try:
        if runtime.llm_orchestrator is None:
            raise VerificationError("direct_llm_runtime_missing")
        async with database.session_factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            before_traces = int(
                await session.scalar(select(func.count()).select_from(QueryTrace)) or 0
            )
            service = get_chat_service(session, settings, runtime)
            repository = NoWriteChatRepository(session)
            service.repository = repository

            supported = await service.answer(SUPPORTED_QUERY)
            trace = supported.retrieval_trace
            if supported.refusal or trace is None:
                raise VerificationError("supported_query_refused")
            if not supported.citations or supported.answer_support_validated is not True:
                raise VerificationError("grounded_answer_not_validated")
            supported_tokens = _token_count(supported.token_usage_json)
            if supported_tokens <= 0:
                raise VerificationError("direct_llm_tokens_missing")
            if not trace.bm25_results or not trace.vector_results or not trace.final_results:
                raise VerificationError("supported_retrieval_missing_results")
            if trace.rerank_metadata.get("applied") is not True:
                raise VerificationError("supported_rerank_not_applied")
            llm_latency_ms = float(supported.stage_timings_ms.get("direct_llm", 0.0))
            if llm_latency_ms <= 0:
                raise VerificationError("direct_llm_latency_missing")

            out_of_scope = await service.answer(OUT_OF_SCOPE_QUERY)
            refusal_trace = out_of_scope.retrieval_trace
            if not out_of_scope.refusal or out_of_scope.citations or refusal_trace is None:
                raise VerificationError("out_of_scope_query_not_refused")
            decision = out_of_scope.evidence_sufficiency
            if decision is None or decision.sufficient:
                raise VerificationError("out_of_scope_evidence_gate_passed")
            if decision.reason != "insufficient_evidence_relevance":
                raise VerificationError("unexpected_out_of_scope_reason")
            if _token_count(out_of_scope.token_usage_json) != 0:
                raise VerificationError("out_of_scope_called_direct_llm")
            if out_of_scope.cost != Decimal(0):
                raise VerificationError("out_of_scope_incurred_llm_cost")
            if not refusal_trace.bm25_results or not refusal_trace.vector_results:
                raise VerificationError("out_of_scope_retrieval_missing_results")
            if refusal_trace.rerank_metadata.get("applied") is not True:
                raise VerificationError("out_of_scope_rerank_not_applied")

            after_traces = int(
                await session.scalar(select(func.count()).select_from(QueryTrace)) or 0
            )
            if before_traces != after_traces or len(repository.traces) != 2:
                raise VerificationError("production_trace_write_boundary_failed")

            print(
                "production_grounded_rag=PASS-LIVE "
                f"embedding_model={settings.embedding_model} "
                f"bm25_hits={len(trace.bm25_results)} vector_hits={len(trace.vector_results)} "
                f"fusion_hits={len(trace.fusion_results)} rerank_hits={len(trace.rerank_results)} "
                f"final_hits={len(trace.final_results)} rerank_model={settings.rerank_model} "
                f"llm_model={runtime.llm_orchestrator.model_name} "
                f"direct_llm_latency_ms={llm_latency_ms:.3f} citations={len(supported.citations)} "
                f"tokens_positive=true answer_support_validated=true"
            )
            print(
                "production_out_of_scope_refusal=PASS-LIVE "
                f"reason={decision.reason} bm25_hits={len(refusal_trace.bm25_results)} "
                f"vector_hits={len(refusal_trace.vector_results)} "
                f"rerank_hits={len(refusal_trace.rerank_results)} direct_llm_called=false"
            )
            print(
                "production_write_boundary=PASS-LIVE transaction_read_only=true "
                "production_trace_writes=0 in_memory_traces=2"
            )
            await session.rollback()
    finally:
        await runtime.close()
        await database.dispose()


try:
    asyncio.run(main())
except Exception as exc:  # noqa: BLE001 - suppress provider response details.
    print(f"production_rag_verify=FAIL error_type={type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1) from None
