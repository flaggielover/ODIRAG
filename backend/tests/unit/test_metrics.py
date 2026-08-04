from __future__ import annotations

from app.metrics import MetricsRegistry


async def test_metrics_registry_reports_bounded_latency_percentiles() -> None:
    registry = MetricsRegistry()
    for duration_ms in (10, 20, 30, 40, 100):
        await registry.record("POST", "/api/chat", 200, duration_ms / 1000)
    for duration_ms in (1, 2, 3, 4, 10):
        registry.record_database(duration_ms / 1000)

    snapshot = await registry.snapshot()
    route = snapshot["routes"][0]
    database = snapshot["database_latency"]

    assert route["sample_count"] == 5
    assert route["p50_latency_ms"] == 30
    assert route["p95_latency_ms"] == 100
    assert route["p99_latency_ms"] == 100
    assert database["sample_count"] == 5
    assert database["p50_latency_ms"] == 3
    assert database["p95_latency_ms"] == 10
