from __future__ import annotations

import asyncio
import math
import re
import time
from collections import Counter, defaultdict, deque
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from statistics import mean
from threading import Lock
from typing import Any, Protocol

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
)
from prometheus_client import Counter as PrometheusCounter
from sqlalchemy import Engine, event
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.routing import Match

_MAX_ROUTE_LABELS = 256
_MAX_PROVIDER_LABELS = 32
_UNMATCHED_ROUTE = "<unmatched>"
_OTHER_ROUTE = "<other>"
_LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9_.:/<>-]{1,64}$")
_HTTP_METHODS = frozenset(
    {"CONNECT", "DELETE", "GET", "HEAD", "OPTIONS", "PATCH", "POST", "PUT", "TRACE"}
)
_STATUS_CLASSES = frozenset({"1xx", "2xx", "3xx", "4xx", "5xx"})
_OUTCOMES = frozenset({"success", "error", "refusal", "skipped"})
_PROVIDER_OPERATIONS = frozenset({"embed_query", "generate_answer", "rerank", "vector_search"})
_REFUSAL_REASONS = frozenset(
    {
        "answer_contains_unsupported_exact_values",
        "insufficient_evidence_relevance",
        "model_output_invalid",
        "model_refusal",
        "query_has_no_substantive_aspects",
        "other",
    }
)
_HTTP_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30)
_RAG_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 60)
_ERROR_CATEGORIES = frozenset(
    {
        "none",
        "cancelled",
        "timeout",
        "transport",
        "http_4xx",
        "http_5xx",
        "missing_credentials",
        "invalid_response",
        "provider_error",
        "unexpected",
    }
)

RAG_STAGES = frozenset(
    {
        "embedding",
        "vector_retrieval",
        "bm25",
        "hybrid",
        "rerank",
        "direct_llm",
        "end_to_end",
        "refusal",
        "error",
    }
)


class MetricsRecorder(Protocol):
    """Small synchronous recorder contract used by async RAG services.

    Implementations must keep labels bounded and must never persist request
    content, credentials, request IDs, or provider exception text.
    """

    def record_provider(
        self,
        provider: str,
        operation: str,
        outcome: str,
        duration_seconds: float,
        *,
        error_category: str | None = None,
    ) -> None: ...

    def record_rag_stage(
        self,
        stage: str,
        outcome: str,
        duration_seconds: float,
        *,
        error_category: str | None = None,
    ) -> None: ...


@dataclass(slots=True)
class MetricsRegistry:
    """Bounded in-process metrics with an isolated Prometheus registry.

    The existing JSON snapshot fields intentionally remain unchanged.  The
    Prometheus collectors are registered on a per-application registry rather
    than the process-global default, so tests and multiple app instances do
    not collide.
    """

    started_at: float = field(default_factory=time.time)
    request_count: Counter[tuple[str, str, int]] = field(default_factory=Counter)
    request_duration_seconds: defaultdict[tuple[str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    request_duration_samples: defaultdict[tuple[str, str], deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    database_duration_samples: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    prometheus_registry: CollectorRegistry = field(
        default_factory=CollectorRegistry,
        repr=False,
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _route_label_lock: Lock = field(default_factory=Lock, repr=False)
    _route_labels: set[str] = field(default_factory=set, repr=False)
    _provider_label_lock: Lock = field(default_factory=Lock, repr=False)
    _provider_labels: set[str] = field(default_factory=set, repr=False)
    _http_requests_total: Any = field(init=False, repr=False)
    _http_duration: Any = field(init=False, repr=False)
    _http_in_flight: Any = field(init=False, repr=False)
    _http_exceptions_total: Any = field(init=False, repr=False)
    _database_duration: Any = field(init=False, repr=False)
    _database_errors_total: Any = field(init=False, repr=False)
    _provider_requests_total: Any = field(init=False, repr=False)
    _provider_duration: Any = field(init=False, repr=False)
    _rag_requests_total: Any = field(init=False, repr=False)
    _rag_duration: Any = field(init=False, repr=False)
    _rag_stage_total: Any = field(init=False, repr=False)
    _rag_stage_duration: Any = field(init=False, repr=False)
    _rag_candidate_count: Any = field(init=False, repr=False)
    _rag_grounded_answers_total: Any = field(init=False, repr=False)
    _rag_refusals_total: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        # Names include the conventional suffixes so exposition consumers can
        # discover stable metric families without relying on implementation
        # details of the Python client.
        self._http_requests_total = PrometheusCounter(
            "odirag_http_requests_total",
            "HTTP requests completed by route template and status class.",
            ("method", "route", "status_class"),
            registry=self.prometheus_registry,
        )
        self._http_duration = Histogram(
            "odirag_http_request_duration_seconds",
            "HTTP request latency by route template and status class.",
            ("method", "route", "status_class"),
            buckets=_HTTP_BUCKETS,
            registry=self.prometheus_registry,
        )
        self._http_in_flight = Gauge(
            "odirag_http_requests_in_flight",
            "HTTP requests currently in flight.",
            ("method", "route"),
            registry=self.prometheus_registry,
        )
        self._http_exceptions_total = PrometheusCounter(
            "odirag_http_exceptions_total",
            "Unhandled HTTP exceptions by route template and bounded category.",
            ("route", "error_category"),
            registry=self.prometheus_registry,
        )
        self._database_duration = Histogram(
            "odirag_database_query_duration_seconds",
            "SQLAlchemy query latency without SQL text labels.",
            buckets=_HTTP_BUCKETS,
            registry=self.prometheus_registry,
        )
        self._database_errors_total = PrometheusCounter(
            "odirag_database_query_errors_total",
            "SQLAlchemy query failures without SQL or exception labels.",
            registry=self.prometheus_registry,
        )
        self._provider_requests_total = PrometheusCounter(
            "odirag_provider_requests_total",
            "Provider operations by bounded provider, operation, and outcome.",
            ("provider", "operation", "outcome", "error_category"),
            registry=self.prometheus_registry,
        )
        self._rag_requests_total = PrometheusCounter(
            "odirag_rag_requests_total",
            "Completed RAG requests by bounded status.",
            ("status",),
            registry=self.prometheus_registry,
        )
        self._rag_duration = Histogram(
            "odirag_rag_duration_seconds",
            "End-to-end RAG request latency by bounded status.",
            ("status",),
            buckets=_RAG_BUCKETS,
            registry=self.prometheus_registry,
        )
        self._provider_duration = Histogram(
            "odirag_provider_request_duration_seconds",
            "Provider operation latency by bounded labels.",
            ("provider", "operation", "outcome", "error_category"),
            buckets=_RAG_BUCKETS,
            registry=self.prometheus_registry,
        )
        self._rag_stage_total = PrometheusCounter(
            "odirag_rag_stage_total",
            "RAG stage outcomes by bounded stage and error category.",
            ("stage", "outcome", "error_category"),
            registry=self.prometheus_registry,
        )
        self._rag_candidate_count = Histogram(
            "odirag_rag_candidate_count",
            "RAG candidate counts at fixed pipeline stages.",
            ("stage",),
            buckets=(0, 1, 3, 5, 8, 10, 20, 50, 100, 200),
            registry=self.prometheus_registry,
        )
        self._rag_grounded_answers_total = PrometheusCounter(
            "odirag_rag_grounded_answers_total",
            "Grounded RAG answers that passed support validation.",
            registry=self.prometheus_registry,
        )
        self._rag_refusals_total = PrometheusCounter(
            "odirag_rag_refusals_total",
            "RAG refusals by a bounded safe reason.",
            ("reason",),
            registry=self.prometheus_registry,
        )
        self._rag_stage_duration = Histogram(
            "odirag_rag_stage_duration_seconds",
            "RAG stage latency by bounded stage and outcome.",
            ("stage", "outcome", "error_category"),
            buckets=_RAG_BUCKETS,
            registry=self.prometheus_registry,
        )

    async def record(
        self, method: str, path: str, status_code: int, duration_seconds: float
    ) -> None:
        """Record the legacy JSON request sample and Prometheus HTTP series."""

        route = self.route_label(path)
        duration = max(0.0, duration_seconds)
        async with self._lock:
            self.request_count[(method, route, status_code)] += 1
            self.request_duration_seconds[(method, route)] += duration
            self.request_duration_samples[(method, route)].append(duration)
        self._safe_http_observation(method, route, status_code, duration)

    def record_http_in_flight(self, method: str, route: str, delta: int) -> None:
        route_label = self.route_label(route)
        if delta == 0:
            return
        try:
            self._http_in_flight.labels(method=_safe_method(method), route=route_label).inc(delta)
        except Exception:
            return

    def record_http_exception(self, route: str, error_category: str) -> None:
        try:
            self._http_exceptions_total.labels(
                route=self.route_label(route),
                error_category=_safe_error_category(error_category),
            ).inc()
        except Exception:
            return

    def record_provider(
        self,
        provider: str,
        operation: str,
        outcome: str,
        duration_seconds: float,
        *,
        error_category: str | None = None,
    ) -> None:
        provider_label = self._bounded_provider_label(provider)
        operation_label = operation if operation in _PROVIDER_OPERATIONS else "unknown"
        outcome_label = _safe_outcome(outcome)
        error_label = _safe_error_category(error_category)
        try:
            labels = self._provider_requests_total.labels(
                provider=provider_label,
                operation=operation_label,
                outcome=outcome_label,
                error_category=error_label,
            )
            labels.inc()
            self._provider_duration.labels(
                provider=provider_label,
                operation=operation_label,
                outcome=outcome_label,
                error_category=error_label,
            ).observe(max(0.0, duration_seconds))
        except Exception:
            # Observability must never turn a provider response into an app
            # failure (for example, during a collector reload).
            return

    def record_rag_stage(
        self,
        stage: str,
        outcome: str,
        duration_seconds: float,
        *,
        error_category: str | None = None,
    ) -> None:
        stage_label = stage if stage in RAG_STAGES else "error"
        outcome_label = _safe_outcome(outcome)
        error_label = _safe_error_category(error_category)
        try:
            self._rag_stage_total.labels(
                stage=stage_label,
                outcome=outcome_label,
                error_category=error_label,
            ).inc()
            self._rag_stage_duration.labels(
                stage=stage_label,
                outcome=outcome_label,
                error_category=error_label,
            ).observe(max(0.0, duration_seconds))
        except Exception:
            return

    def record_rag_request(
        self,
        status: str,
        duration_seconds: float,
        *,
        grounded: bool = False,
        refusal_reason: str | None = None,
        candidate_counts: dict[str, int] | None = None,
    ) -> None:
        status_label = status if status in {"success", "refusal", "error"} else "error"
        try:
            self._rag_requests_total.labels(status=status_label).inc()
            self._rag_duration.labels(status=status_label).observe(max(0.0, duration_seconds))
            if grounded:
                self._rag_grounded_answers_total.inc()
            if status_label == "refusal":
                reason = refusal_reason if refusal_reason in _REFUSAL_REASONS else "other"
                self._rag_refusals_total.labels(reason=reason).inc()
            for stage, count in (candidate_counts or {}).items():
                if stage in {"retrieved", "reranked", "final"}:
                    self._rag_candidate_count.labels(stage=stage).observe(max(0, count))
        except Exception:
            return

    def record_database(self, duration_seconds: float) -> None:
        duration = max(0.0, duration_seconds)
        self.database_duration_samples.append(duration)
        with suppress(Exception):
            self._database_duration.observe(duration)

    def attach_database_engine(self, engine: Engine) -> None:
        @event.listens_for(engine, "before_cursor_execute")
        def before_cursor_execute(
            connection: Any,
            _cursor: Any,
            _statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            connection.info.setdefault("odirag_query_started", []).append(time.perf_counter())

        @event.listens_for(engine, "after_cursor_execute")
        def after_cursor_execute(
            connection: Any,
            _cursor: Any,
            _statement: str,
            _parameters: Any,
            _context: Any,
            _executemany: bool,
        ) -> None:
            starts = connection.info.get("odirag_query_started")
            if starts:
                self.record_database(time.perf_counter() - starts.pop())

        @event.listens_for(engine, "handle_error")
        def handle_error(exception_context: Any) -> None:
            with suppress(Exception):
                connection = getattr(exception_context, "connection", None)
                starts = (
                    connection.info.get("odirag_query_started") if connection is not None else None
                )
                if starts:
                    starts.pop()
                self._database_errors_total.inc()

    def route_label(self, path: str | None) -> str:
        """Return a bounded route template label, never a query-bearing URL."""

        candidate = path or _UNMATCHED_ROUTE
        if "?" in candidate:
            candidate = candidate.split("?", 1)[0]
        if not candidate.startswith("/"):
            candidate = _UNMATCHED_ROUTE
        if len(candidate) > 128:
            candidate = _UNMATCHED_ROUTE
        with self._route_label_lock:
            if candidate in self._route_labels:
                return candidate
            if len(self._route_labels) >= _MAX_ROUTE_LABELS:
                return _OTHER_ROUTE
            self._route_labels.add(candidate)
            return candidate

    def prometheus_payload(self) -> bytes:
        """Render the isolated registry; callers should handle render errors."""

        return generate_latest(self.prometheus_registry)

    def _bounded_provider_label(self, provider: str) -> str:
        candidate = _safe_label(provider, "unknown")
        with self._provider_label_lock:
            if candidate in self._provider_labels:
                return candidate
            if len(self._provider_labels) >= _MAX_PROVIDER_LABELS:
                return "other"
            self._provider_labels.add(candidate)
            return candidate

    async def snapshot(self) -> dict[str, object]:
        async with self._lock:
            request_count = self.request_count.copy()
            duration_samples = {
                key: list(samples) for key, samples in self.request_duration_samples.items()
            }
            database_samples = list(self.database_duration_samples)
        total_requests = sum(request_count.values())
        status_counts: Counter[str] = Counter()
        for (_, _, status_code), count in request_count.items():
            status_counts[f"{status_code // 100}xx"] += count
        return {
            "uptime_seconds": round(time.time() - self.started_at, 3),
            "requests_total": total_requests,
            "requests_by_status_class": dict(status_counts),
            "routes": [
                {
                    "method": method,
                    "path": path,
                    "status_code": status_code,
                    "count": count,
                    **_latency_summary(duration_samples.get((method, path), [])),
                }
                for (method, path, status_code), count in sorted(request_count.items())
            ],
            "database_latency": _latency_summary(database_samples),
        }

    def _safe_http_observation(
        self, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        status_class = _status_class(status_code)
        method_label = _safe_method(method)
        try:
            labels = self._http_requests_total.labels(
                method=method_label,
                route=route,
                status_class=status_class,
            )
            labels.inc()
            self._http_duration.labels(
                method=method_label,
                route=route,
                status_class=status_class,
            ).observe(duration_seconds)
        except Exception:
            return


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, registry: MetricsRegistry, api_prefix: str = "") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.registry = registry
        self.api_prefix = api_prefix.rstrip("/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        method = _safe_method(request.method)
        # Resolve through Starlette's route match contract so parameter values
        # never become labels while the request is still in flight.
        pending_route = self.registry.route_label(_resolved_route(request, self.api_prefix))
        self._safe_in_flight(method, pending_route, 1)
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as exc:
            with suppress(Exception):
                self.registry.record_http_exception(
                    _resolved_route(request, self.api_prefix),
                    classify_error(exc),
                )
            raise
        finally:
            route = _resolved_route(request, self.api_prefix)
            self._safe_in_flight(method, pending_route, -1)
            # Metrics are advisory and must not mask handler exceptions.
            with suppress(Exception):
                await self.registry.record(
                    method,
                    route,
                    status_code,
                    time.perf_counter() - started,
                )

    def _safe_in_flight(self, method: str, route: str, delta: int) -> None:
        try:
            self.registry.record_http_in_flight(method, route, delta)
        except Exception:
            return


def classify_error(exc: BaseException | None) -> str:
    """Map provider failures to a small, non-sensitive category set."""

    if exc is None:
        return "none"
    if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt)):
        return "cancelled"
    name = exc.__class__.__name__.lower()
    reason = str(getattr(exc, "reason", "")).lower()
    combined = f"{name} {reason}"
    if "api key" in combined or "credential" in combined:
        return "missing_credentials"
    if "timeout" in combined:
        return "timeout"
    if "transport" in combined or "connection" in combined:
        return "transport"
    match = re.search(r"http(?:_status| status)[_: -]?([45][0-9]{2})", combined)
    if match:
        return f"http_{match.group(1)[0]}xx"
    if "invalid" in combined or "response" in combined or "json" in combined:
        return "invalid_response"
    if isinstance(exc, (ValueError, TypeError, KeyError, IndexError)):
        return "invalid_response"
    return "provider_error" if reason else "unexpected"


def provider_label(provider: object | str) -> str:
    if isinstance(provider, str):
        return _safe_label(provider, "unknown")
    endpoint = getattr(provider, "base_url", None) or getattr(provider, "url", None)
    if isinstance(endpoint, str):
        lowered = endpoint.lower()
        if "dashscope.aliyuncs.com" in lowered:
            return "bailian"
        if "cohere.com" in lowered:
            return "cohere"
        if "deepseek.com" in lowered:
            return "deepseek"
        if "qdrant" in lowered:
            return "qdrant"
    wrapped_provider = getattr(provider, "provider", None)
    if wrapped_provider is not None and wrapped_provider is not provider:
        return provider_label(wrapped_provider)
    value = getattr(provider, "provider_name", None)
    if isinstance(value, str) and value:
        return _safe_label(value, "unknown")
    name = type(provider).__name__
    name = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", name).lower()
    return _safe_label(name, "unknown")


def _resolved_route(request: Request, api_prefix: str) -> str:
    route = request.scope.get("route")
    route_path = getattr(route, "path", None)
    if isinstance(route_path, str) and route_path:
        request_path = str(request.scope.get("path", ""))
        prefix = api_prefix.rstrip("/")
        if prefix and request_path.startswith(f"{prefix}/") and not route_path.startswith(prefix):
            return f"{prefix}{route_path}"
        return route_path

    router = getattr(request.app, "router", None)
    partial_path: str | None = None
    for candidate in getattr(router, "routes", ()):
        try:
            match, _child_scope = candidate.matches(request.scope)
        except Exception:
            continue
        candidate_path = getattr(candidate, "path", None)
        if not isinstance(candidate_path, str) or not candidate_path:
            continue
        if match is Match.FULL:
            return candidate_path
        if match is Match.PARTIAL and partial_path is None:
            partial_path = candidate_path
    return partial_path or _UNMATCHED_ROUTE


def _safe_label(value: str, fallback: str) -> str:
    normalized = value.strip()[:64]
    return normalized if _LABEL_PATTERN.fullmatch(normalized) else fallback


def _safe_outcome(value: str) -> str:
    return value if value in _OUTCOMES else "error"


def _safe_method(value: str) -> str:
    normalized = value.strip().upper()
    return normalized if normalized in _HTTP_METHODS else "OTHER"


def _safe_error_category(value: str | None) -> str:
    return value if value in _ERROR_CATEGORIES else ("none" if value is None else "unexpected")


def _status_class(status_code: int) -> str:
    value = f"{status_code // 100}xx"
    return value if value in _STATUS_CLASSES else "5xx"


def _latency_summary(values_seconds: Iterable[float]) -> dict[str, int | float]:
    values_ms = sorted(value * 1000 for value in values_seconds)
    return {
        "sample_count": len(values_ms),
        "average_latency_ms": mean(values_ms) if values_ms else 0.0,
        "p50_latency_ms": _percentile(values_ms, 0.50),
        "p95_latency_ms": _percentile(values_ms, 0.95),
        "p99_latency_ms": _percentile(values_ms, 0.99),
    }


def _percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    index = max(0, math.ceil(quantile * len(values)) - 1)
    return values[index]


__all__ = [
    "CONTENT_TYPE_LATEST",
    "RAG_STAGES",
    "MetricsMiddleware",
    "MetricsRecorder",
    "MetricsRegistry",
    "classify_error",
    "provider_label",
]
