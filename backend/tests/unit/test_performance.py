from app.performance import latency_report, percentile


def test_latency_report_uses_nearest_rank_and_keeps_goals_separate() -> None:
    values = [10.0, 20.0, 30.0, 40.0, 100.0]

    report = latency_report(
        values,
        request_count=6,
        error_count=1,
        elapsed_seconds=2.0,
        goal_p95_ms=90.0,
    )

    assert percentile(values, 0.50) == 30.0
    assert report["success_count"] == 5
    assert report["error_rate"] == 1 / 6
    assert report["requests_per_second"] == 3.0
    assert report["p95_latency_ms"] == 100.0
    assert report["goal_p95_ms"] == 90.0
    assert report["goal_met"] is False
