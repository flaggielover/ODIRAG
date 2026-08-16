from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest


def _benchmark_module() -> ModuleType:
    path = Path(__file__).resolve().parents[3] / "scripts" / "benchmark_rag_performance.py"
    spec = importlib.util.spec_from_file_location("benchmark_rag_performance", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _trace(*, candidate_count: int, applied: bool) -> dict[str, object]:
    reranked_count = candidate_count if applied else 0
    timings: dict[str, float] = {"total": 10.0}
    if applied:
        timings["retrieval_rerank"] = 1.0
    return {
        "trace_id": "trace-1",
        "user_query": "question",
        "stage_timings_json": timings,
        "rerank_metadata_json": {
            "provider": "remote",
            "candidate_count": candidate_count,
            "reranked_count": reranked_count,
            "applied": applied,
            "error": None,
            "error_code": None,
        },
    }


def test_phase_ab_dataset_selects_fixed_twenty_cases() -> None:
    benchmark = _benchmark_module()
    dataset = (
        Path(__file__).resolve().parents[3] / "data" / "evaluation" / "phase_ab_benchmark.json"
    )

    cases = benchmark._load_cases(dataset)

    assert len(cases) == 20
    assert cases[0]["id"] == "phase-j-draft-001"
    assert cases[-1]["id"] == "phase-j-draft-020"
    assert sum(bool(case["expected_refusal"]) for case in cases) == 10


def test_empty_candidates_make_remote_rerank_not_applicable() -> None:
    benchmark = _benchmark_module()

    matched, applied = benchmark._validate_response(
        {"id": "case-1", "query": "question", "expected_refusal": True},
        {"refusal": True, "citations": []},
        _trace(candidate_count=0, applied=False),
    )

    assert matched is True
    assert applied is False


def test_candidates_require_remote_rerank_to_be_applied() -> None:
    benchmark = _benchmark_module()

    with pytest.raises(ValueError, match="remote_rerank_guard_failed"):
        benchmark._validate_response(
            {"id": "case-1", "query": "question", "expected_refusal": True},
            {"refusal": True, "citations": []},
            _trace(candidate_count=8, applied=False),
        )


def test_post_change_benchmark_requires_current_stage_instrumentation() -> None:
    benchmark = _benchmark_module()
    trace = _trace(candidate_count=0, applied=False)
    trace["stage_timings_json"]["direct_llm"] = 4.0

    with pytest.raises(ValueError, match="stale_stage_timings"):
        benchmark._validate_response(
            {"id": "case-1", "query": "question", "expected_refusal": True},
            {"refusal": True, "citations": []},
            trace,
            require_current_instrumentation=True,
        )


def test_pre_llm_refusal_does_not_require_context_packing() -> None:
    benchmark = _benchmark_module()

    matched, applied = benchmark._validate_response(
        {"id": "case-1", "query": "question", "expected_refusal": True},
        {"refusal": True, "citations": []},
        _trace(candidate_count=0, applied=False),
        require_current_instrumentation=True,
    )

    assert matched is True
    assert applied is False


def test_benchmark_base_url_protects_admin_credentials() -> None:
    benchmark = _benchmark_module()

    benchmark._validate_base_url("http://127.0.0.1:8080/api")
    benchmark._validate_base_url("https://rag.example/api")

    with pytest.raises(ValueError, match="must use HTTPS"):
        benchmark._validate_base_url("http://rag.example/api")
    with pytest.raises(ValueError, match="must not contain credentials"):
        benchmark._validate_base_url("https://admin:secret@rag.example/api")
