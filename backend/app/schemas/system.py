from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

DependencyState = Literal["healthy", "unavailable", "disabled"]


class DependencyHealth(BaseModel):
    status: DependencyState
    latency_ms: float | None = None
    detail: str | None = None


class HealthResponse(BaseModel):
    status: Literal["healthy", "degraded"]
    service: str
    environment: str
    checked_at: datetime
    dependencies: dict[str, DependencyHealth]


class CozeCrawlConfigResponse(BaseModel):
    enabled: bool
    token_configured: bool
    legacy_workflow_configured: bool
    batch_workflow_configured: bool
    default_contract: Literal["legacy_single_article", "batch_crawl"]


class CozeStatusResponse(BaseModel):
    enabled: bool
    token_configured: bool
    legacy_workflow_configured: bool
    batch_workflow_configured: bool
    default_contract: Literal["legacy_single_article", "batch_crawl"]


class RouteMetric(BaseModel):
    method: str
    path: str
    status_code: int
    count: int
    sample_count: int
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float


class LatencyMetric(BaseModel):
    sample_count: int
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float


class CrawlerMetrics(BaseModel):
    window_hours: int
    task_count: int
    status_counts: dict[str, int]
    task_failure_rate: float
    discovered_count: int
    fetched_count: int
    success_count: int
    failed_count: int
    item_failure_rate: float


class KnowledgeMetrics(BaseModel):
    document_count: int
    final_status_counts: dict[str, int]
    index_status_counts: dict[str, int]
    approved_count: int
    indexed_count: int
    index_failure_count: int
    stale_count: int
    chunk_count: int


class RagMetrics(BaseModel):
    window_hours: int
    query_count: int
    refusal_count: int
    refusal_rate: float
    average_latency_ms: float
    p50_latency_ms: float
    p95_latency_ms: float
    total_tokens: int
    measured_token_trace_count: int
    total_cost: Decimal
    average_cost: Decimal
    trace_completeness_rate: float
    evaluation_regression_count: int


class MetricsResponse(BaseModel):
    uptime_seconds: float
    requests_total: int
    requests_by_status_class: dict[str, int]
    routes: list[RouteMetric]
    database_latency: LatencyMetric
    crawler: CrawlerMetrics
    knowledge: KnowledgeMetrics
    rag: RagMetrics
    dependencies: dict[str, DependencyHealth]
