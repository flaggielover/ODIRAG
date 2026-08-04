from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MetricDelta:
    name: str
    baseline: float
    candidate: float
    delta: float
    regression: bool


def compare_metrics(
    baseline: dict[str, float],
    candidate: dict[str, float],
    *,
    lower_is_better: frozenset[str] = frozenset({"latency", "cost", "hallucination_rate"}),
    tolerance: float = 0.0,
) -> list[MetricDelta]:
    if baseline.keys() != candidate.keys():
        raise ValueError("baseline and candidate must contain identical metric names")
    comparisons: list[MetricDelta] = []
    for name in sorted(baseline):
        before, after = float(baseline[name]), float(candidate[name])
        delta = after - before
        regression = delta > tolerance if name in lower_is_better else delta < -tolerance
        comparisons.append(MetricDelta(name, before, after, delta, regression))
    return comparisons
