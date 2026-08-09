from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from statistics import mean
from typing import Any

from app.config import Settings
from app.errors import NotFoundError
from app.models import Alert, QueryTrace
from app.repositories.observability import (
    CitationLineageContext,
    ObservabilityRepository,
)
from app.schemas.observability import (
    AnswerLineageResponse,
    ChunkLineageResponse,
    CitationLineageResponse,
    CrawlTaskLineageResponse,
    DocumentLineageResponse,
    DocumentVersionLineageResponse,
    SourceLineageResponse,
)
from app.schemas.system import (
    CrawlerMetrics,
    DependencyHealth,
    HealthResponse,
    KnowledgeMetrics,
    RagMetrics,
)


@dataclass(frozen=True, slots=True)
class OperationalMetrics:
    crawler: CrawlerMetrics
    knowledge: KnowledgeMetrics
    rag: RagMetrics


@dataclass(frozen=True, slots=True)
class AlertCandidate:
    alert_key: str
    alert_type: str
    severity: str
    component: str
    message: str
    observed_value: float
    threshold_value: float
    details: dict[str, Any]


class LineageService:
    def __init__(self, repository: ObservabilityRepository) -> None:
        self.repository = repository

    async def answer_lineage(self, trace_id: str) -> AnswerLineageResponse:
        trace = await self.repository.get_trace(trace_id)
        if trace is None:
            raise NotFoundError("Query trace", trace_id)
        citations = []
        for raw_citation in trace.citations_json:
            citation = {str(key): value for key, value in raw_citation.items()}
            chunk_id = str(citation.get("chunk_id", ""))
            context = await self.repository.citation_lineage(chunk_id) if chunk_id else None
            citations.append(_citation_lineage(citation, context))
        return AnswerLineageResponse(
            trace_id=trace.trace_id,
            answer=trace.answer,
            prompt_version=trace.prompt_version,
            prompt_snapshot=trace.prompt_snapshot_json,
            citations=citations,
        )


class MonitoringService:
    def __init__(
        self,
        repository: ObservabilityRepository,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.settings = settings

    async def metrics(self) -> OperationalMetrics:
        since = datetime.now(UTC) - timedelta(hours=self.settings.alert_window_hours)
        crawler = await self.repository.crawler_aggregate(since)
        knowledge = await self.repository.knowledge_aggregate()
        traces = await self.repository.recent_traces(since)
        regressions = await self.repository.regression_experiment_count(since)
        task_count = sum(crawler.status_counts.values())
        failed_tasks = crawler.status_counts.get("failed", 0)
        document_count = sum(knowledge.final_status_counts.values())
        return OperationalMetrics(
            crawler=CrawlerMetrics(
                window_hours=self.settings.alert_window_hours,
                task_count=task_count,
                status_counts=crawler.status_counts,
                task_failure_rate=_ratio(failed_tasks, task_count),
                discovered_count=crawler.discovered_count,
                fetched_count=crawler.fetched_count,
                success_count=crawler.success_count,
                failed_count=crawler.failed_count,
                item_failure_rate=_ratio(crawler.failed_count, crawler.fetched_count),
            ),
            knowledge=KnowledgeMetrics(
                document_count=document_count,
                final_status_counts=knowledge.final_status_counts,
                index_status_counts=knowledge.index_status_counts,
                approved_count=knowledge.final_status_counts.get("approved", 0),
                indexed_count=knowledge.index_status_counts.get("indexed", 0),
                index_failure_count=knowledge.index_status_counts.get("failed", 0),
                stale_count=knowledge.index_status_counts.get("stale", 0),
                chunk_count=knowledge.chunk_count,
            ),
            rag=_rag_metrics(traces, regressions, self.settings.alert_window_hours),
        )

    async def refresh_alerts(
        self,
        metrics: OperationalMetrics,
        health: HealthResponse,
    ) -> list[Alert]:
        candidates = alert_candidates(metrics, health.dependencies, self.settings)
        now = datetime.now(UTC)
        active_keys = {candidate.alert_key for candidate in candidates}
        for candidate in candidates:
            alert = await self.repository.get_alert_by_key(candidate.alert_key)
            if alert is None:
                await self.repository.add_alert(
                    Alert(
                        alert_key=candidate.alert_key,
                        alert_type=candidate.alert_type,
                        severity=candidate.severity,
                        status="open",
                        component=candidate.component,
                        message=candidate.message,
                        observed_value=Decimal(str(candidate.observed_value)),
                        threshold_value=Decimal(str(candidate.threshold_value)),
                        details_json=candidate.details,
                        occurrence_count=1,
                        first_seen_at=now,
                        last_seen_at=now,
                    )
                )
                continue
            alert.severity = candidate.severity
            alert.component = candidate.component
            alert.message = candidate.message
            alert.observed_value = Decimal(str(candidate.observed_value))
            alert.threshold_value = Decimal(str(candidate.threshold_value))
            alert.details_json = candidate.details
            alert.occurrence_count += 1
            alert.last_seen_at = now
            if alert.status == "resolved":
                alert.status = "open"
                alert.resolved_at = None
                alert.acknowledged_at = None
        for alert in await self.repository.open_alerts():
            if alert.alert_key.startswith("monitor:") and alert.alert_key not in active_keys:
                alert.status = "resolved"
                alert.resolved_at = now
        await self.repository.commit()
        return await self.repository.list_alerts(limit=500)

    async def acknowledge(self, alert_id: int) -> Alert:
        alert = await self._alert(alert_id)
        if alert.status != "resolved":
            alert.status = "acknowledged"
            alert.acknowledged_at = datetime.now(UTC)
            await self.repository.commit()
        return await self.repository.refresh(alert)

    async def resolve(self, alert_id: int) -> Alert:
        alert = await self._alert(alert_id)
        alert.status = "resolved"
        alert.resolved_at = datetime.now(UTC)
        await self.repository.commit()
        return await self.repository.refresh(alert)

    async def _alert(self, alert_id: int) -> Alert:
        alert = await self.repository.get_alert(alert_id)
        if alert is None:
            raise NotFoundError("Alert", alert_id)
        return alert


def alert_candidates(
    metrics: OperationalMetrics,
    dependencies: dict[str, DependencyHealth],
    settings: Settings,
) -> list[AlertCandidate]:
    candidates: list[AlertCandidate] = []
    crawler = metrics.crawler
    if (
        crawler.task_count >= settings.alert_minimum_sample_size
        and crawler.task_failure_rate >= settings.alert_crawl_failure_rate
    ):
        candidates.append(
            AlertCandidate(
                "monitor:crawler:failure_rate",
                "high_failure_rate",
                "high",
                "crawler",
                "Crawler task failure rate exceeded the configured threshold.",
                crawler.task_failure_rate,
                settings.alert_crawl_failure_rate,
                {
                    "task_count": crawler.task_count,
                    "status_counts": crawler.status_counts,
                },
            )
        )
    if metrics.knowledge.index_failure_count >= settings.alert_index_failure_count:
        candidates.append(
            AlertCandidate(
                "monitor:knowledge:index_failures",
                "index_failures",
                "high",
                "knowledge",
                "One or more documents are in the failed index state.",
                float(metrics.knowledge.index_failure_count),
                float(settings.alert_index_failure_count),
                {"index_status_counts": metrics.knowledge.index_status_counts},
            )
        )
    for name, dependency in sorted(dependencies.items()):
        if dependency.status == "unavailable":
            candidates.append(
                AlertCandidate(
                    f"monitor:dependency:{name}",
                    "service_unavailable",
                    "critical" if name == "database" else "high",
                    name,
                    f"Dependency {name} is unavailable.",
                    1.0,
                    0.0,
                    {"detail": dependency.detail, "latency_ms": dependency.latency_ms},
                )
            )
    rag = metrics.rag
    if (
        rag.query_count >= settings.alert_minimum_sample_size
        and rag.p95_latency_ms >= settings.alert_chat_p95_ms
    ):
        candidates.append(
            AlertCandidate(
                "monitor:rag:p95_latency",
                "latency_regression",
                "high",
                "rag",
                "RAG P95 latency exceeded the configured threshold.",
                rag.p95_latency_ms,
                settings.alert_chat_p95_ms,
                {"query_count": rag.query_count},
            )
        )
    if rag.evaluation_regression_count >= settings.alert_evaluation_regression_count:
        candidates.append(
            AlertCandidate(
                "monitor:evaluation:regression",
                "evaluation_regression",
                "critical",
                "evaluation",
                "Completed experiments reported evaluation regressions.",
                float(rag.evaluation_regression_count),
                float(settings.alert_evaluation_regression_count),
                {"window_hours": rag.window_hours},
            )
        )
    if (
        rag.query_count >= settings.alert_minimum_sample_size
        and float(rag.average_cost) >= settings.alert_average_cost
    ):
        candidates.append(
            AlertCandidate(
                "monitor:rag:average_cost",
                "abnormal_cost",
                "warning",
                "rag",
                "Average RAG cost exceeded the configured threshold.",
                float(rag.average_cost),
                settings.alert_average_cost,
                {"query_count": rag.query_count, "total_cost": str(rag.total_cost)},
            )
        )
    return candidates


def _citation_lineage(
    citation: dict[str, Any],
    context: CitationLineageContext | None,
) -> CitationLineageResponse:
    if context is None:
        return CitationLineageResponse(
            citation=citation,
            chunk=None,
            document=None,
            document_version=None,
            crawl_task=None,
            source=None,
            lineage_ids=[],
            complete=False,
            missing_steps=[
                "chunk",
                "document",
                "document_version",
                "crawl_task",
                "source",
            ],
        )
    chunk = context.chunk
    document = context.document
    version = context.document_version
    crawl = context.crawl_task
    source = context.source
    missing = []
    if version is None:
        missing.append("document_version")
    if crawl is None:
        missing.append("crawl_task")
    if source is None:
        missing.append("source")
    return CitationLineageResponse(
        citation=citation,
        chunk=ChunkLineageResponse(
            id=chunk.id,
            chunk_id=chunk.chunk_id,
            chunk_index=chunk.chunk_index,
            section_path=chunk.section_path,
            section_title=chunk.section_title,
            page_number=chunk.page_number,
            content_hash=chunk.content_hash,
        ),
        document=DocumentLineageResponse(
            id=document.id,
            document_id=document.document_id,
            title=document.title,
            source_url=document.source_url,
            version=document.version,
        ),
        document_version=(
            DocumentVersionLineageResponse(
                id=version.id,
                version=version.version,
                content_hash=version.content_hash,
                changed_fields=version.changed_fields_json,
                created_at=version.created_at,
            )
            if version is not None
            else None
        ),
        crawl_task=(
            CrawlTaskLineageResponse(
                id=crawl.id,
                status=crawl.status,
                task_type=crawl.task_type,
                trigger_type=crawl.trigger_type,
                created_at=crawl.created_at,
                started_at=crawl.started_at,
                finished_at=crawl.finished_at,
            )
            if crawl is not None
            else None
        ),
        source=(
            SourceLineageResponse(
                id=source.id,
                source_key=source.source_key,
                name=source.name,
                homepage_url=source.homepage_url,
                official_status=source.official_status,
            )
            if source is not None
            else None
        ),
        lineage_ids=[lineage.lineage_id for lineage in context.lineage_records],
        complete=not missing,
        missing_steps=missing,
    )


def _rag_metrics(traces: list[QueryTrace], regression_count: int, window_hours: int) -> RagMetrics:
    latencies = sorted(float(trace.latency_ms) for trace in traces)
    costs = [Decimal(trace.cost) for trace in traces]
    token_counts = [_trace_tokens(trace.token_usage_json) for trace in traces]
    measured_tokens = [value for value in token_counts if value is not None]
    complete = sum(
        trace.answer is not None
        and bool(trace.prompt_snapshot_json)
        and isinstance(trace.token_usage_json, dict)
        for trace in traces
    )
    total_cost = sum(costs, start=Decimal("0"))
    evidence_decisions = [
        trace.evidence_decision_json
        for trace in traces
        if isinstance(trace.evidence_decision_json, dict)
        and isinstance(trace.evidence_decision_json.get("sufficient"), bool)
    ]
    evidence_sufficient = sum(decision.get("sufficient") is True for decision in evidence_decisions)
    evidence_latencies = [
        float(value)
        for decision in evidence_decisions
        if isinstance((value := decision.get("latency_ms")), (int, float))
        and not isinstance(value, bool)
        and value >= 0
    ]
    answered_rag = [trace for trace in traces if trace.query_type != "sql" and not trace.refusal]
    citation_answers = sum(bool(trace.citations_json) for trace in answered_rag)
    grounding_failures = sum(
        trace.refusal and decision.get("sufficient") is True
        for trace, decision in (
            (trace, trace.evidence_decision_json)
            for trace in traces
            if isinstance(trace.evidence_decision_json, dict)
        )
    )
    return RagMetrics(
        window_hours=window_hours,
        query_count=len(traces),
        refusal_count=sum(trace.refusal for trace in traces),
        refusal_rate=_ratio(sum(trace.refusal for trace in traces), len(traces)),
        average_latency_ms=mean(latencies) if latencies else 0.0,
        p50_latency_ms=_percentile(latencies, 0.50),
        p95_latency_ms=_percentile(latencies, 0.95),
        total_tokens=sum(measured_tokens),
        measured_token_trace_count=len(measured_tokens),
        total_cost=total_cost,
        average_cost=total_cost / len(traces) if traces else Decimal("0"),
        trace_completeness_rate=_ratio(complete, len(traces)),
        evaluation_regression_count=regression_count,
        evidence_assessed_count=len(evidence_decisions),
        evidence_sufficient_count=evidence_sufficient,
        evidence_insufficient_count=len(evidence_decisions) - evidence_sufficient,
        evidence_sufficiency_rate=_ratio(evidence_sufficient, len(evidence_decisions)),
        average_evidence_gate_latency_ms=(mean(evidence_latencies) if evidence_latencies else 0.0),
        grounding_failure_count=grounding_failures,
        citation_answer_count=citation_answers,
        citation_rate=_ratio(citation_answers, len(answered_rag)),
        refusal_citation_violation_count=sum(
            trace.refusal and bool(trace.citations_json) for trace in traces
        ),
    )


def _trace_tokens(payload: dict[str, Any]) -> int | None:
    for key in ("total_tokens", "tokens", "token_count"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    prompt = payload.get("prompt_tokens")
    completion = payload.get("completion_tokens")
    values = [
        value
        for value in (prompt, completion)
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ]
    return sum(values) if values else None


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(quantile * len(values)) - 1)
    return values[index]
