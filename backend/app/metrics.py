from __future__ import annotations

import asyncio
import math
import time
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from statistics import mean
from typing import Any

from fastapi import Request, Response
from sqlalchemy import Engine, event
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


@dataclass(slots=True)
class MetricsRegistry:
    started_at: float = field(default_factory=time.time)
    request_count: Counter[tuple[str, str, int]] = field(default_factory=Counter)
    request_duration_seconds: defaultdict[tuple[str, str], float] = field(
        default_factory=lambda: defaultdict(float)
    )
    request_duration_samples: defaultdict[tuple[str, str], deque[float]] = field(
        default_factory=lambda: defaultdict(lambda: deque(maxlen=1000))
    )
    database_duration_samples: deque[float] = field(default_factory=lambda: deque(maxlen=5000))
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def record(
        self, method: str, path: str, status_code: int, duration_seconds: float
    ) -> None:
        async with self._lock:
            self.request_count[(method, path, status_code)] += 1
            self.request_duration_seconds[(method, path)] += duration_seconds
            self.request_duration_samples[(method, path)].append(duration_seconds)

    def record_database(self, duration_seconds: float) -> None:
        self.database_duration_samples.append(max(0.0, duration_seconds))

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


class MetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, registry: MetricsRegistry, api_prefix: str = "") -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self.registry = registry
        self.api_prefix = api_prefix.rstrip("/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        route_path = str(getattr(route, "path", request.url.path))
        path = (
            f"{self.api_prefix}{route_path}"
            if self.api_prefix and not route_path.startswith(self.api_prefix)
            else route_path
        )
        await self.registry.record(
            request.method,
            str(path),
            response.status_code,
            time.perf_counter() - started,
        )
        return response


def _latency_summary(values_seconds: list[float]) -> dict[str, int | float]:
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
