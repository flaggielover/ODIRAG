from __future__ import annotations

import asyncio
import math
import os
import sys
import time
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select, text

from app.api.routes.chat import get_chat_service
from app.config import get_settings
from app.dependencies import get_current_user
from app.main import create_app
from app.metrics import provider_label
from app.models import QueryTrace
from app.repositories.chat import ChatRepository

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
REQUEST_REPEATS = 3
MAX_REQUESTS = REQUEST_REPEATS * 2
METRICS_OUTPUT = Path("/tmp/odirag-phase3-rag.prom")


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


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _token_count(payload: dict[str, object]) -> int:
    total = payload.get("total_tokens")
    if isinstance(total, int) and not isinstance(total, bool):
        return total
    return sum(
        value
        for value in (payload.get("prompt_tokens"), payload.get("completion_tokens"))
        if isinstance(value, int) and not isinstance(value, bool)
    )


def _atomic_write_metrics(payload: bytes) -> None:
    temp = METRICS_OUTPUT.with_suffix(".prom.tmp")
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temp, flags, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.chmod(temp, 0o600)
    os.replace(temp, METRICS_OUTPUT)


def _assert_supported_response(body: dict[str, Any]) -> None:
    if body.get("refusal") is True:
        raise VerificationError("supported_query_refused")
    if not body.get("citations"):
        raise VerificationError("supported_query_has_no_citations")


def _assert_refusal_response(body: dict[str, Any]) -> None:
    if body.get("refusal") is not True:
        raise VerificationError("out_of_scope_query_not_refused")
    if body.get("citations"):
        raise VerificationError("out_of_scope_query_has_citations")
    decision = body.get("evidence_sufficiency")
    if not isinstance(decision, dict) or decision.get("sufficient") is not False:
        raise VerificationError("out_of_scope_evidence_gate_passed")


async def main() -> None:
    settings = get_settings().model_copy(update={"bootstrap_admin": False})
    if settings.embedding_model != "text-embedding-v4":
        raise VerificationError("unexpected_embedding_model")
    if settings.embedding_dimensions != 1536:
        raise VerificationError("unexpected_embedding_dimensions")
    if settings.rerank_model != "rerank-v3.5":
        raise VerificationError("unexpected_rerank_model")
    if settings.llm_provider != "direct" or settings.answer_provider != "llm":
        raise VerificationError("unexpected_llm_configuration")

    app = create_app(settings)
    latencies: list[float] = []
    started = time.perf_counter()
    async with app.router.lifespan_context(app):
        database = app.state.database
        runtime = app.state.runtime
        metrics = app.state.metrics
        async with database.session_factory() as session:
            await session.execute(text("SET TRANSACTION READ ONLY"))
            before_traces = int(
                await session.scalar(select(func.count()).select_from(QueryTrace)) or 0
            )
            service = get_chat_service(session, settings, runtime)
            repository = NoWriteChatRepository(session)
            service.repository = repository
            app.dependency_overrides[get_chat_service] = lambda: service
            app.dependency_overrides[get_current_user] = lambda: object()

            embedding_started = time.perf_counter()
            try:
                vector = await runtime.embedding_provider.embed_query(SUPPORTED_QUERY)
            except Exception as exc:
                metrics.record_provider(
                    provider_label(runtime.embedding_provider),
                    "embed_query",
                    "error",
                    time.perf_counter() - embedding_started,
                    error_category="provider_error",
                )
                raise VerificationError("embedding_provider_smoke_failed") from exc
            embedding_duration = time.perf_counter() - embedding_started
            if len(vector) != settings.embedding_dimensions:
                raise VerificationError("embedding_vector_length_mismatch")
            metrics.record_provider(
                provider_label(runtime.embedding_provider),
                "embed_query",
                "success",
                embedding_duration,
            )

            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://phase3.internal",
                timeout=settings.dependency_timeout_seconds * 6,
            ) as client:
                for _ in range(REQUEST_REPEATS):
                    request_started = time.perf_counter()
                    supported = await client.post(
                        f"{settings.api_prefix}/chat", json={"query": SUPPORTED_QUERY}
                    )
                    latencies.append(time.perf_counter() - request_started)
                    if supported.status_code != 200:
                        raise VerificationError("supported_request_failed")
                    _assert_supported_response(supported.json())

                    request_started = time.perf_counter()
                    refusal = await client.post(
                        f"{settings.api_prefix}/chat", json={"query": OUT_OF_SCOPE_QUERY}
                    )
                    latencies.append(time.perf_counter() - request_started)
                    if refusal.status_code != 200:
                        raise VerificationError("refusal_request_failed")
                    _assert_refusal_response(refusal.json())

            after_traces = int(
                await session.scalar(select(func.count()).select_from(QueryTrace)) or 0
            )
            if before_traces != after_traces:
                raise VerificationError("production_trace_write_boundary_failed")
            if len(repository.traces) != MAX_REQUESTS:
                raise VerificationError("unexpected_in_memory_trace_count")
            if any(_token_count(trace.token_usage_json) <= 0 for trace in repository.traces[::2]):
                raise VerificationError("direct_llm_tokens_missing")
            if any(trace.cost != Decimal(0) for trace in repository.traces[1::2]):
                raise VerificationError("refusal_incurred_llm_cost")

            payload = metrics.prometheus_payload()
            forbidden = (SUPPORTED_QUERY.encode(), OUT_OF_SCOPE_QUERY.encode(), b"Authorization")
            if any(value in payload for value in forbidden):
                raise VerificationError("metrics_payload_contains_request_data")
            for expected in (b'provider="bailian"', b'provider="cohere"', b'provider="deepseek"'):
                if expected not in payload:
                    raise VerificationError("provider_metric_missing")
            _atomic_write_metrics(payload)
            await session.rollback()
            app.dependency_overrides.clear()

    duration = time.perf_counter() - started
    print(
        "observability_sample=PASS-LIVE "
        f"max_requests={MAX_REQUESTS} completed={len(latencies)} errors=0 "
        f"duration_seconds={duration:.3f}"
    )
    print(
        "observability_wall_latency "
        f"p50_seconds={_percentile(latencies, 0.50):.3f} "
        f"p95_seconds={_percentile(latencies, 0.95):.3f} "
        f"p99_seconds={_percentile(latencies, 0.99):.3f}"
    )
    print(
        "observability_providers=PASS-LIVE "
        "bailian=true qdrant=true cohere=true deepseek=true "
        f"embedding_vector_length={settings.embedding_dimensions}"
    )
    print(
        "observability_write_boundary=PASS-LIVE "
        f"transaction_read_only=true production_trace_writes=0 in_memory_traces={MAX_REQUESTS}"
    )


try:
    asyncio.run(main())
except Exception as exc:
    if isinstance(exc, VerificationError):
        print(f"observability_sample=FAIL error_code={exc}", file=sys.stderr)
    else:
        print(f"observability_sample=FAIL error_type={type(exc).__name__}", file=sys.stderr)
    raise SystemExit(1) from None
