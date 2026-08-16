#!/usr/bin/env python3
"""Run a fixed, real /api/chat latency benchmark without weakening RAG gates."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from ipaddress import ip_address
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "data" / "evaluation" / "phase_ab_benchmark.json"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/api")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=DEFAULT_DATASET,
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--warmup", type=int, default=3)
    parser.add_argument("--case-offset", type=int, default=0)
    parser.add_argument("--case-limit", type=int)
    parser.add_argument("--delay-seconds", type=float, default=0.0)
    parser.add_argument("--collect-existing", action="store_true")
    parser.add_argument("--trace-limit", type=int, default=500)
    parser.add_argument("--resume-prefix-count", type=int, default=0)
    parser.add_argument("--prior-warmup-count", type=int, default=0)
    parser.add_argument("--max-transient-retries", type=int, default=2)
    parser.add_argument("--require-expected-outcomes", action="store_true")
    parser.add_argument("--quality-only", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "performance")
    return parser.parse_args()


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percentile * len(ordered)))
    return round(ordered[rank - 1], 3)


def _summary(values: list[float]) -> dict[str, float | int | None]:
    return {
        "count": len(values),
        "p50_ms": _percentile(values, 0.50),
        "p75_ms": _percentile(values, 0.75),
        "p95_ms": _percentile(values, 0.95),
        "p99_ms": _percentile(values, 0.99),
        "max_ms": round(max(values), 3) if values else None,
    }


def _validate_base_url(value: str) -> None:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base-url must be an absolute HTTP(S) URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("base-url must not contain credentials, query, or fragment")
    if parsed.scheme == "https" or parsed.hostname.lower() == "localhost":
        return
    try:
        is_loopback = ip_address(parsed.hostname).is_loopback
    except ValueError:
        is_loopback = False
    if not is_loopback:
        raise ValueError("non-loopback base-url must use HTTPS")


def _stage_summaries(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_stage: dict[str, list[float]] = {}
    for sample in samples:
        for stage, value in sample["stage_timings_ms"].items():
            by_stage.setdefault(stage, []).append(float(value))
    return {stage: _summary(values) for stage, values in sorted(by_stage.items())}


def _load_cases(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    case_ids = payload.get("case_ids")
    if isinstance(case_ids, list):
        source_name = payload.get("source_dataset")
        if not isinstance(source_name, str) or not source_name:
            raise ValueError("benchmark dataset source_dataset is missing")
        source_path = (path.parent / source_name).resolve()
        source_payload = json.loads(source_path.read_text(encoding="utf-8"))
        source_cases = source_payload.get("cases")
        if not isinstance(source_cases, list):
            raise TypeError("benchmark source dataset has no cases")
        by_id = {case.get("id"): case for case in source_cases}
        missing = [case_id for case_id in case_ids if case_id not in by_id]
        if missing:
            raise ValueError(f"benchmark case IDs are missing: {', '.join(missing)}")
        cases = [
            {
                "id": case_id,
                "query": by_id[case_id]["question"],
                "expected_refusal": bool(by_id[case_id].get("should_refuse")),
                "category": by_id[case_id].get("category"),
                "difficulty": by_id[case_id].get("difficulty"),
                "human_verified": False,
            }
            for case_id in case_ids
        ]
    else:
        cases = payload.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("benchmark dataset has no cases")
    if any(case.get("human_verified") is True for case in cases):
        raise ValueError("performance dataset must not claim human verification")
    return cases


async def _request(
    client: httpx.AsyncClient,
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    response = await client.request(method, path, json=payload)
    response.raise_for_status()
    body = response.json()
    return body


def _validate_response(
    case: dict[str, Any],
    answer: dict[str, Any],
    trace: dict[str, Any],
    *,
    require_current_instrumentation: bool = False,
) -> tuple[bool, bool]:
    expected_refusal = bool(case.get("expected_refusal", False))
    actual_refusal = bool(answer.get("refusal"))
    if trace.get("user_query") != case.get("query"):
        raise ValueError(f"query_round_trip_failed:{case.get('id')}")
    timings = trace.get("stage_timings_json")
    if not isinstance(timings, dict) or not timings.get("total"):
        raise ValueError(f"missing_stage_timings:{case.get('id')}")
    if (
        require_current_instrumentation
        and "direct_llm" in timings
        and "context_packing" not in timings
    ):
        raise ValueError(f"stale_stage_timings:{case.get('id')}")
    rerank = trace.get("rerank_metadata_json")
    if not isinstance(rerank, dict) or rerank.get("provider") != "remote":
        raise ValueError(f"remote_rerank_guard_failed:{case.get('id')}")
    candidate_count = rerank.get("candidate_count")
    if not isinstance(candidate_count, int) or candidate_count < 0:
        raise ValueError(f"remote_rerank_guard_failed:{case.get('id')}")
    rerank_applied = rerank.get("applied") is True
    if candidate_count > 0:
        if (
            not rerank_applied
            or rerank.get("error") is not None
            or rerank.get("error_code") is not None
            or not isinstance(rerank.get("reranked_count"), int)
            or int(rerank["reranked_count"]) <= 0
            or not isinstance(timings.get("retrieval_rerank"), (int, float))
            or float(timings["retrieval_rerank"]) <= 0
        ):
            raise ValueError(f"remote_rerank_guard_failed:{case.get('id')}")
    elif (
        rerank_applied
        or rerank.get("reranked_count") != 0
        or rerank.get("error") is not None
        or rerank.get("error_code") is not None
    ):
        raise ValueError(f"empty_candidate_rerank_guard_failed:{case.get('id')}")
    if actual_refusal:
        if answer.get("citations"):
            raise ValueError(f"refusal_citation_guard_failed:{case.get('id')}")
    else:
        if not answer.get("citations"):
            raise ValueError(f"supported_guard_failed:{case.get('id')}")
        evidence = answer.get("evidence_sufficiency")
        if not isinstance(evidence, dict) or evidence.get("sufficient") is not True:
            raise ValueError(f"evidence_guard_failed:{case.get('id')}")
    return actual_refusal == expected_refusal, rerank_applied


def _sample(
    *,
    case: dict[str, Any],
    answer: dict[str, Any],
    trace: dict[str, Any],
    run: int,
    elapsed_ms: float,
    http_elapsed_ms: float | None,
    expected_outcome_matched: bool,
    rerank_applied: bool,
) -> dict[str, Any]:
    timings = {
        key: value
        for key, value in trace["stage_timings_json"].items()
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    }
    return {
        "run": run,
        "case_id": case["id"],
        "trace_id": trace["trace_id"],
        "refusal": bool(answer.get("refusal")),
        "expected_refusal": bool(case.get("expected_refusal")),
        "expected_outcome_matched": expected_outcome_matched,
        "remote_rerank_applied": rerank_applied,
        "citation_count": len(answer.get("citations") or []),
        "elapsed_ms": elapsed_ms,
        "http_elapsed_ms": http_elapsed_ms,
        "stage_timings_ms": timings,
    }


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    password = os.getenv("ODIRAG_ADMIN_PASSWORD")
    if not password:
        return {"status": "BLOCKED", "reason": "ODIRAG_ADMIN_PASSWORD missing"}
    _validate_base_url(args.base_url)
    if args.collect_existing and args.quality_only:
        raise ValueError("collect-existing and quality-only cannot be combined")
    if args.collect_existing and args.resume_prefix_count:
        raise ValueError("collect-existing and resume-prefix-count cannot be combined")
    if args.quality_only and args.resume_prefix_count:
        raise ValueError("quality-only and resume-prefix-count cannot be combined")
    if args.quality_only:
        args.require_expected_outcomes = True
    cases = _load_cases(args.dataset)
    if args.runs < 1 or args.warmup < 0 or args.case_offset < 0:
        raise ValueError("runs must be positive and offsets/warmup must not be negative")
    if args.warmup > 5:
        raise ValueError("warmup must not exceed 5 requests")
    if args.case_limit is not None and args.case_limit < 1:
        raise ValueError("case-limit must be positive")
    if (
        args.resume_prefix_count < 0
        or args.prior_warmup_count < 0
        or args.max_transient_retries < 0
    ):
        raise ValueError("resume, warmup, and retry counts must be non-negative")
    if args.warmup + args.prior_warmup_count > 5:
        raise ValueError("combined warmup requests must not exceed 5")
    if args.delay_seconds < 0:
        raise ValueError("delay-seconds must not be negative")
    cases = cases[
        args.case_offset : (
            args.case_offset + args.case_limit if args.case_limit is not None else None
        )
    ]
    if not cases:
        raise ValueError("benchmark case selection is empty")
    if args.resume_prefix_count > len(cases):
        raise ValueError("resume-prefix-count exceeds selected case count")
    planned_requests = len(cases) * args.runs - args.resume_prefix_count
    if not args.collect_existing and planned_requests > 90:
        raise ValueError("formal benchmark requests must not exceed 90")
    timeout = httpx.Timeout(120.0, connect=10.0)
    all_samples: list[dict[str, Any]] = []
    run_summaries: list[dict[str, Any]] = []
    formal_request_count = 0
    transient_retry_count = 0
    async with httpx.AsyncClient(
        base_url=args.base_url.rstrip("/") + "/", timeout=timeout
    ) as client:
        login = await _request(
            client,
            "POST",
            "auth/login",
            {
                "username": os.getenv("ODIRAG_ADMIN_USERNAME", "admin"),
                "password": password,
            },
        )
        if not isinstance(login, dict):
            raise TypeError("authentication response is not an object")
        token = login.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("authentication_failed")
        client.headers["Authorization"] = f"Bearer {token}"
        if args.collect_existing:
            traces = await _request(client, "GET", f"chat/traces?limit={args.trace_limit}")
            if not isinstance(traces, list):
                raise TypeError("trace list response is not an array")
            for case in cases:
                matching = [
                    trace
                    for trace in traces
                    if isinstance(trace, dict)
                    and trace.get("user_query") == case["query"]
                    and isinstance(trace.get("rerank_metadata_json"), dict)
                    and trace["rerank_metadata_json"].get("provider") == "remote"
                ]
                if not matching:
                    raise ValueError(f"missing_remote_trace:{case.get('id')}")
                trace = max(matching, key=lambda item: str(item.get("created_at") or ""))
                answer = {
                    "refusal": trace.get("refusal"),
                    "citations": trace.get("citations_json") or [],
                    "evidence_sufficiency": trace.get("evidence_decision_json") or {},
                }
                expected_outcome_matched, rerank_applied = _validate_response(case, answer, trace)
                all_samples.append(
                    _sample(
                        case=case,
                        answer=answer,
                        trace=trace,
                        run=0,
                        elapsed_ms=float(trace["latency_ms"]),
                        http_elapsed_ms=None,
                        expected_outcome_matched=expected_outcome_matched,
                        rerank_applied=rerank_applied,
                    )
                )
            run_summaries.append(
                {
                    "run": "latest_remote_trace",
                    "overall": _summary([s["elapsed_ms"] for s in all_samples]),
                    "stages": _stage_summaries(all_samples),
                }
            )
        else:
            for index in range(args.warmup):
                case = cases[index % len(cases)]
                await _request(
                    client,
                    "POST",
                    "chat",
                    {"query": case["query"], "filters": {}},
                )
                if args.delay_seconds and index < args.warmup - 1:
                    await asyncio.sleep(args.delay_seconds)
            resumed_samples: list[dict[str, Any]] = []
            if args.resume_prefix_count:
                traces = await _request(client, "GET", f"chat/traces?limit={args.trace_limit}")
                if not isinstance(traces, list):
                    raise TypeError("trace list response is not an array")
                for case in cases[: args.resume_prefix_count]:
                    matching = [
                        trace
                        for trace in traces
                        if isinstance(trace, dict)
                        and trace.get("user_query") == case["query"]
                        and isinstance(trace.get("rerank_metadata_json"), dict)
                        and trace["rerank_metadata_json"].get("provider") == "remote"
                    ]
                    if not matching:
                        raise ValueError(f"missing_resume_trace:{case.get('id')}")
                    trace = max(matching, key=lambda item: str(item.get("created_at") or ""))
                    answer = {
                        "refusal": trace.get("refusal"),
                        "citations": trace.get("citations_json") or [],
                        "evidence_sufficiency": trace.get("evidence_decision_json") or {},
                    }
                    expected_outcome_matched, rerank_applied = _validate_response(
                        case,
                        answer,
                        trace,
                        require_current_instrumentation=True,
                    )
                    resumed_samples.append(
                        _sample(
                            case=case,
                            answer=answer,
                            trace=trace,
                            run=1,
                            elapsed_ms=float(trace["latency_ms"]),
                            http_elapsed_ms=None,
                            expected_outcome_matched=expected_outcome_matched,
                            rerank_applied=rerank_applied,
                        )
                    )
            for run_number in range(1, args.runs + 1):
                run_samples = list(resumed_samples) if run_number == 1 else []
                if run_number == 1:
                    all_samples.extend(resumed_samples)
                selected_cases = cases[args.resume_prefix_count :] if run_number == 1 else cases
                for case_index, case in enumerate(selected_cases):
                    while True:
                        if formal_request_count >= 90:
                            raise ValueError("formal benchmark request cap reached")
                        started = time.perf_counter()
                        formal_request_count += 1
                        try:
                            answer = await _request(
                                client,
                                "POST",
                                "chat",
                                {"query": case["query"], "filters": {}},
                            )
                            break
                        except httpx.HTTPStatusError as exc:
                            if (
                                exc.response.status_code not in {429, 502, 503, 504}
                                or transient_retry_count >= args.max_transient_retries
                            ):
                                raise
                            transient_retry_count += 1
                            await asyncio.sleep(max(args.delay_seconds, 10.0))
                    if not isinstance(answer, dict):
                        raise TypeError("chat response is not an object")
                    elapsed = round((time.perf_counter() - started) * 1000, 3)
                    trace_id = answer.get("trace_id")
                    if not isinstance(trace_id, str) or not trace_id:
                        raise ValueError(f"missing_trace_id:{case.get('id')}")
                    trace = await _request(client, "GET", f"chat/traces/{trace_id}")
                    if not isinstance(trace, dict):
                        raise TypeError("trace response is not an object")
                    expected_outcome_matched, rerank_applied = _validate_response(
                        case,
                        answer,
                        trace,
                        require_current_instrumentation=True,
                    )
                    sample = _sample(
                        case=case,
                        answer=answer,
                        trace=trace,
                        run=run_number,
                        elapsed_ms=float(trace["latency_ms"]),
                        http_elapsed_ms=elapsed,
                        expected_outcome_matched=expected_outcome_matched,
                        rerank_applied=rerank_applied,
                    )
                    run_samples.append(sample)
                    all_samples.append(sample)
                    if args.delay_seconds and (
                        case_index < len(selected_cases) - 1 or run_number < args.runs
                    ):
                        await asyncio.sleep(args.delay_seconds)
                run_summaries.append(
                    {
                        "run": run_number,
                        "overall": _summary([s["elapsed_ms"] for s in run_samples]),
                        "stages": _stage_summaries(run_samples),
                    }
                )
    by_stage: dict[str, list[float]] = {}
    for sample in all_samples:
        for stage, value in sample["stage_timings_ms"].items():
            by_stage.setdefault(stage, []).append(float(value))
    overall_summary = _summary([sample["elapsed_ms"] for sample in all_samples])
    overall_p95 = overall_summary["p95_ms"]
    latency_target_met = bool(isinstance(overall_p95, (int, float)) and overall_p95 < 5000)
    matched_count = sum(1 for sample in all_samples if sample["expected_outcome_matched"])
    mismatched_count = len(all_samples) - matched_count
    rerank_applied_count = sum(1 for sample in all_samples if sample["remote_rerank_applied"])
    rerank_status = "PASS-LIVE" if rerank_applied_count > 0 else "NOT-EXERCISED"
    if args.collect_existing:
        status = "BASELINE-LIVE-PROFILE"
    elif args.quality_only:
        status = (
            "PASS-LIVE-QUALITY-REGRESSION"
            if mismatched_count == 0 and rerank_applied_count > 0
            else "FAIL-LIVE-QUALITY-REGRESSION"
        )
    else:
        status = (
            "PASS-LIVE-LATENCY-ONLY"
            if latency_target_met
            and rerank_applied_count > 0
            and (not args.require_expected_outcomes or mismatched_count == 0)
            else "PARTIAL-LIVE-PERFORMANCE"
        )
    dataset_payload = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = {
        "status": status,
        "phase": "before_optimization" if args.collect_existing else "after_optimization",
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": str(args.dataset),
        "dataset_status": dataset_payload.get("dataset_status", "PERFORMANCE_ONLY_UNVERIFIED"),
        "runs": args.runs,
        "warmup_request_count": args.warmup + args.prior_warmup_count,
        "prior_warmup_request_count": args.prior_warmup_count,
        "case_count": len(cases),
        "sample_count": len(all_samples),
        "formal_request_count": 0 if args.collect_existing else formal_request_count,
        "resumed_sample_count": args.resume_prefix_count,
        "transient_retry_count": transient_retry_count,
        "measurement_source": (
            "persisted_trace_latency_ms" if args.collect_existing else "query_trace_latency_ms"
        ),
        "run_summaries": run_summaries,
        "overall": overall_summary,
        "stages": {stage: _summary(values) for stage, values in sorted(by_stage.items())},
        "expected_outcomes": {
            "matched": matched_count,
            "mismatched": mismatched_count,
            "required": args.require_expected_outcomes,
            "status": (
                "PASS-LIVE"
                if args.require_expected_outcomes and mismatched_count == 0
                else (
                    "FAIL-LIVE"
                    if args.require_expected_outcomes
                    else "PERFORMANCE-ONLY-NOT-HUMAN-GOLD"
                )
            ),
        },
        "rerank_coverage": {
            "applied": rerank_applied_count,
            "not_applicable_empty_candidates": sum(
                1 for sample in all_samples if not sample["remote_rerank_applied"]
            ),
        },
        "cache_regime": {
            "warmup_requests_total": args.warmup + args.prior_warmup_count,
            "run_1": "partially_warm",
            "later_runs": "eligible_for_real_query_cache_hits",
            "per_run_stage_summaries_recorded": True,
        },
        "quality_guard": (
            "PASS-LIVE"
            if args.quality_only and mismatched_count == 0
            else ("FAIL-LIVE" if args.quality_only else "SEPARATE-LIVE-REGRESSION-REQUIRED")
        ),
        "p95_target_ms": 5000,
        "p95_target_met": latency_target_met,
        "remote_rerank": rerank_status,
        "brave_source_discovery": "NOT_CALLED",
        "samples": all_samples,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    position = "before" if args.collect_existing else "after"
    output = args.output_dir / f"phase-ab-{position}-{stamp}.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["output"] = str(output)
    return report


def main() -> int:
    arguments = _args()
    try:
        report = __import__("asyncio").run(_run(arguments))
    except (httpx.HTTPError, OSError, TypeError, ValueError) as exc:
        print(json.dumps({"status": "FAIL-LIVE", "reason": str(exc)}, ensure_ascii=False))
        return 1
    console_report = {key: value for key, value in report.items() if key != "samples"}
    print(json.dumps(console_report, ensure_ascii=False, indent=2))
    if report["status"] == "BLOCKED":
        return 3
    if report["status"] == "BASELINE-LIVE-PROFILE":
        return 0
    return 0 if str(report["status"]).startswith("PASS-LIVE") else 2


if __name__ == "__main__":
    sys.exit(main())
