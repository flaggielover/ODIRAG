from __future__ import annotations

import math
from statistics import mean


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def latency_report(
    values_ms: list[float],
    *,
    request_count: int,
    error_count: int,
    elapsed_seconds: float,
    goal_p95_ms: float,
) -> dict[str, int | float | bool]:
    return {
        "request_count": request_count,
        "success_count": max(0, request_count - error_count),
        "error_count": error_count,
        "error_rate": error_count / request_count if request_count else 0.0,
        "requests_per_second": request_count / elapsed_seconds if elapsed_seconds > 0 else 0.0,
        "average_latency_ms": mean(values_ms) if values_ms else 0.0,
        "p50_latency_ms": percentile(values_ms, 0.50),
        "p95_latency_ms": percentile(values_ms, 0.95),
        "p99_latency_ms": percentile(values_ms, 0.99),
        "goal_p95_ms": goal_p95_ms,
        "goal_met": bool(values_ms) and percentile(values_ms, 0.95) < goal_p95_ms,
    }
