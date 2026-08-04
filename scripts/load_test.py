from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.performance import latency_report


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    path: str
    payload: dict[str, Any]
    goal_p95_ms: float


SCENARIOS = (
    Scenario(
        "search",
        "search",
        {"query": "软件企业研发投入支持措施", "mode": "hybrid_rerank", "filters": {}},
        1500.0,
    ),
    Scenario(
        "chat",
        "chat",
        {"query": "软件企业研发投入支持措施", "filters": {}},
        5000.0,
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a lightweight authenticated ODIRAG load test"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    parser.add_argument(
        "--username", default=os.getenv("ODIRAG_LOAD_TEST_USERNAME", "admin")
    )
    parser.add_argument("--password", default=os.getenv("ODIRAG_LOAD_TEST_PASSWORD"))
    parser.add_argument(
        "--requests", type=int, default=30, help="Requests per scenario"
    )
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data" / "load-tests")
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    if not args.password:
        raise SystemExit("Set ODIRAG_LOAD_TEST_PASSWORD or pass --password")
    if args.requests < 1 or args.concurrency < 1 or args.warmup < 0:
        raise SystemExit(
            "requests/concurrency must be positive and warmup must not be negative"
        )

    timeout = httpx.Timeout(30.0, connect=5.0)
    limits = httpx.Limits(
        max_connections=args.concurrency, max_keepalive_connections=args.concurrency
    )
    async with httpx.AsyncClient(
        base_url=f"{args.base_url.rstrip('/')}/",
        timeout=timeout,
        limits=limits,
    ) as client:
        login = await client.post(
            "auth/login",
            json={"username": args.username, "password": args.password},
        )
        login.raise_for_status()
        token = login.json()["access_token"]
        client.headers["Authorization"] = f"Bearer {token}"

        reports: dict[str, dict[str, int | float | bool]] = {}
        errors: dict[str, list[str]] = {}
        for scenario in SCENARIOS:
            for _ in range(args.warmup):
                warmup = await client.post(scenario.path, json=scenario.payload)
                warmup.raise_for_status()
            samples, failures, elapsed = await _run_scenario(
                client,
                scenario,
                requests=args.requests,
                concurrency=args.concurrency,
            )
            reports[scenario.name] = latency_report(
                samples,
                request_count=args.requests,
                error_count=len(failures),
                elapsed_seconds=elapsed,
                goal_p95_ms=scenario.goal_p95_ms,
            )
            errors[scenario.name] = failures[:20]

        metrics = await client.get("system/metrics")
        metrics.raise_for_status()
        database = metrics.json()["database_latency"]
        database["goal_p95_ms"] = 300.0
        database["goal_met"] = database["p95_latency_ms"] < 300.0

    generated_at = datetime.now(UTC)
    payload = {
        "generated_at": generated_at.isoformat(),
        "base_url": args.base_url,
        "concurrency": args.concurrency,
        "requests_per_scenario": args.requests,
        "warmup_requests": args.warmup,
        "scenarios": reports,
        "database": database,
        "errors": errors,
        "note": "Thresholds are engineering goals; measurements are reported without rewriting results.",
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stem = generated_at.strftime("%Y%m%dT%H%M%SZ")
    json_path = args.output_dir / f"load-test-{stem}.json"
    markdown_path = args.output_dir / f"load-test-{stem}.md"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown_path.write_text(_markdown(payload), encoding="utf-8")
    print(
        json.dumps(
            {"json": str(json_path), "markdown": str(markdown_path)}, ensure_ascii=False
        )
    )
    return 2 if any(errors.values()) else 0


async def _run_scenario(
    client: httpx.AsyncClient,
    scenario: Scenario,
    *,
    requests: int,
    concurrency: int,
) -> tuple[list[float], list[str], float]:
    semaphore = asyncio.Semaphore(concurrency)

    async def request_once() -> tuple[float | None, str | None]:
        async with semaphore:
            started = time.perf_counter()
            try:
                response = await client.post(scenario.path, json=scenario.payload)
                elapsed_ms = (time.perf_counter() - started) * 1000
                if response.is_success:
                    return elapsed_ms, None
                return None, f"HTTP {response.status_code}: {response.text[:160]}"
            except httpx.HTTPError as exc:
                return None, exc.__class__.__name__

    started = time.perf_counter()
    results = await asyncio.gather(*(request_once() for _ in range(requests)))
    elapsed = time.perf_counter() - started
    samples = [
        sample for sample, error in results if sample is not None and error is None
    ]
    failures = [error for _sample, error in results if error is not None]
    return samples, failures, elapsed


def _markdown(payload: dict[str, Any]) -> str:
    rows = [
        "# ODIRAG Load Test",
        "",
        f"Generated: `{payload['generated_at']}`",
        "",
        "| Workload | Requests | Errors | RPS | P50 ms | P95 ms | P99 ms | Goal | Met |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | :---: |",
    ]
    for name, report in payload["scenarios"].items():
        rows.append(
            f"| {name} | {report['request_count']} | {report['error_count']} | "
            f"{report['requests_per_second']:.2f} | {report['p50_latency_ms']:.2f} | "
            f"{report['p95_latency_ms']:.2f} | {report['p99_latency_ms']:.2f} | "
            f"<{report['goal_p95_ms']:.0f} ms | {'yes' if report['goal_met'] else 'no'} |"
        )
    database = payload["database"]
    rows.extend(
        [
            "",
            "## Database",
            "",
            (
                f"Observed {database['sample_count']} SQL statements; P95 "
                f"{database['p95_latency_ms']:.2f} ms against the <300 ms engineering goal "
                f"({'met' if database['goal_met'] else 'not met'})."
            ),
            "",
            str(payload["note"]),
            "",
        ]
    )
    return "\n".join(rows)


def main() -> None:
    raise SystemExit(asyncio.run(run(parse_args())))


if __name__ == "__main__":
    main()
