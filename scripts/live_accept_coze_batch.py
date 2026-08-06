#!/usr/bin/env python3
"""Run a bounded live acceptance check through the authenticated ODIRAG API.

The script never prints credentials, Coze deployment URLs, request headers, or raw
provider responses. A successful exit proves that the backend queued a real
``batch_crawl`` task, the worker persisted a Coze invocation, and the normalized
task reached a result-bearing state. It does not approve the returned documents.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

MAX_ARTICLES = 5
MAX_PAGES = 1
RESULT_STATES = {"completed", "partial_failed", "waiting_review"}
FAILED_STATES = {"failed", "cancelled"}
TERMINAL_STATES = RESULT_STATES | FAILED_STATES

EXIT_OK = 0
EXIT_NOT_PUBLISHED = 2
EXIT_CONFIGURATION = 3
EXIT_TASK_FAILED = 4
EXIT_TIMEOUT = 5


@dataclass(slots=True)
class AcceptanceApiError(Exception):
    status_code: int | None
    code: str

    def __str__(self) -> str:
        return self.code


class JsonApi(Protocol):
    def request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any: ...


class ApiClient:
    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.access_token = access_token
        self.timeout_seconds = timeout_seconds

    def request_json(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> Any:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read()
        except HTTPError as exc:
            raise AcceptanceApiError(exc.code, _read_error_code(exc)) from None
        except URLError:
            raise AcceptanceApiError(None, "api_unreachable") from None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise AcceptanceApiError(None, "api_returned_invalid_json") from None


def _read_error_code(error: HTTPError) -> str:
    try:
        payload = json.loads(error.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return "api_request_failed"
    if not isinstance(payload, dict):
        return "api_request_failed"
    detail = payload.get("error")
    if isinstance(detail, dict) and isinstance(detail.get("code"), str):
        return detail["code"]
    return "api_request_failed"


def authenticate(
    base_url: str,
    *,
    username: str,
    password: str,
    timeout_seconds: float,
) -> str:
    anonymous = ApiClient(base_url, timeout_seconds=timeout_seconds)
    payload = anonymous.request_json(
        "POST", "/auth/login", {"username": username, "password": password}
    )
    if not isinstance(payload, dict) or not isinstance(
        payload.get("access_token"), str
    ):
        raise AcceptanceApiError(None, "authentication_response_invalid")
    return payload["access_token"]


def run_acceptance(
    api: JsonApi,
    *,
    source_column_id: int,
    timeout_seconds: float,
    poll_interval_seconds: float,
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[int, dict[str, Any]]:
    config = api.request_json("GET", "/system/coze/status")
    if not isinstance(config, dict):
        return EXIT_CONFIGURATION, {"status": "coze_config_response_invalid"}
    if not config.get("batch_workflow_configured"):
        return EXIT_NOT_PUBLISHED, {"status": "batch_workflow_not_published"}
    if not config.get("enabled"):
        return EXIT_CONFIGURATION, {"status": "coze_disabled"}
    if not config.get("token_configured"):
        return EXIT_CONFIGURATION, {"status": "coze_token_not_configured"}

    task = api.request_json(
        "POST",
        "/crawl-tasks",
        {
            "source_column_id": source_column_id,
            "task_type": "incremental",
            "trigger_type": "manual",
            "execution_mode": "queued",
            "provider": "coze",
            "contract_mode": "batch_crawl",
            "provider_contract": "batch_crawl",
            "max_articles": MAX_ARTICLES,
            "max_pages": MAX_PAGES,
        },
    )
    if not isinstance(task, dict) or not isinstance(task.get("id"), int):
        return EXIT_TASK_FAILED, {"status": "crawl_task_response_invalid"}

    task_id = task["id"]
    deadline = monotonic() + timeout_seconds
    while task.get("status") not in TERMINAL_STATES:
        if monotonic() >= deadline:
            return EXIT_TIMEOUT, {
                "status": "live_acceptance_timeout",
                "task_id": task_id,
                "task_status": task.get("status"),
                "current_stage": task.get("current_stage"),
            }
        sleep(poll_interval_seconds)
        task = api.request_json("GET", f"/crawl-tasks/{task_id}")
        if not isinstance(task, dict):
            return EXIT_TASK_FAILED, {
                "status": "crawl_task_response_invalid",
                "task_id": task_id,
            }

    error_code = task.get("provider_error_code")
    if error_code == "COZE_BATCH_WORKFLOW_NOT_PUBLISHED":
        return EXIT_NOT_PUBLISHED, {
            "status": "batch_workflow_not_published",
            "task_id": task_id,
        }

    invocations = api.request_json("GET", f"/crawl-tasks/{task_id}/invocations")
    if not isinstance(invocations, list):
        invocations = []
    batch_invocations = [
        item
        for item in invocations
        if isinstance(item, dict) and item.get("contract") == "batch_crawl"
    ]
    latest = batch_invocations[0] if batch_invocations else {}
    acceptance = api.request_json(
        "GET", f"/crawl-tasks/{task_id}/acceptance-summary"
    )
    if not isinstance(acceptance, dict):
        return EXIT_TASK_FAILED, {
            "status": "acceptance_summary_invalid",
            "task_id": task_id,
        }
    summary = {
        "status": (
            "live_batch_verified"
            if task.get("status") in RESULT_STATES
            else "task_failed"
        ),
        "task_id": task_id,
        "task_status": task.get("status"),
        "current_stage": task.get("current_stage"),
        "accepted_count": _safe_count(task.get("accepted_count")),
        "success_count": _safe_count(
            task.get("success_count", task.get("accepted_count"))
        ),
        "rejected_count": _safe_count(task.get("rejected_count")),
        "pending_review_count": _safe_count(task.get("pending_review_count")),
        "failed_count": _safe_count(task.get("failed_count")),
        "discovered_count": _safe_count(task.get("discovered_count")),
        "fetched_count": _safe_count(task.get("fetched_count")),
        "database_document_count": _safe_count(
            acceptance.get("database_document_count")
        ),
        "chunk_count": _safe_count(acceptance.get("chunk_count")),
        "qdrant_point_count": _safe_count(acceptance.get("qdrant_point_count")),
        "batch_invocation_count": len(batch_invocations),
        "invocation_status": latest.get("status"),
        "invocation_http_status": latest.get("http_status_code"),
        "provider_error_code": error_code,
        "max_articles": MAX_ARTICLES,
        "max_pages": MAX_PAGES,
    }
    if task.get("status") in FAILED_STATES:
        return EXIT_TASK_FAILED, summary
    if not batch_invocations:
        summary["status"] = "batch_invocation_not_recorded"
        return EXIT_TASK_FAILED, summary
    http_status = latest.get("http_status_code")
    if latest.get("status") != "completed" or not isinstance(http_status, int):
        summary["status"] = "batch_invocation_failed"
        return EXIT_TASK_FAILED, summary
    if not 200 <= http_status < 300:
        summary["status"] = "batch_invocation_failed"
        return EXIT_TASK_FAILED, summary
    if (
        summary["discovered_count"] < 1
        or summary["fetched_count"] < 1
        or summary["database_document_count"] < 1
    ):
        summary["status"] = "batch_result_empty"
        return EXIT_TASK_FAILED, summary
    return EXIT_OK, summary


def _safe_count(value: Any) -> int:
    return value if isinstance(value, int) and value >= 0 else 0


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    source_column_env = os.getenv("ODIRAG_ACCEPTANCE_SOURCE_COLUMN_ID")
    parser.add_argument(
        "--api-base-url",
        default=os.getenv(
            "ODIRAG_ACCEPTANCE_API_BASE_URL", "http://127.0.0.1:8080/api"
        ),
    )
    parser.add_argument(
        "--source-column-id",
        type=_positive_int,
        default=_positive_int(source_column_env) if source_column_env else None,
        required=source_column_env is None,
    )
    parser.add_argument(
        "--username", default=os.getenv("ODIRAG_ADMIN_USERNAME", "admin")
    )
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    access_token = os.getenv("ODIRAG_ACCEPTANCE_ACCESS_TOKEN")
    try:
        if not access_token:
            password = os.getenv("ODIRAG_ADMIN_PASSWORD")
            if not password and sys.stdin.isatty():
                password = getpass.getpass("ODIRAG administrator password: ")
            if not password:
                _print_result({"status": "authentication_required"})
                return EXIT_CONFIGURATION
            access_token = authenticate(
                args.api_base_url,
                username=args.username,
                password=password,
                timeout_seconds=min(args.timeout_seconds, 30.0),
            )
        api = ApiClient(
            args.api_base_url,
            access_token=access_token,
            timeout_seconds=min(args.timeout_seconds, 120.0),
        )
        exit_code, result = run_acceptance(
            api,
            source_column_id=args.source_column_id,
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )
    except AcceptanceApiError as exc:
        result = {"status": exc.code, "http_status": exc.status_code}
        exit_code = EXIT_TASK_FAILED
    except Exception:
        result = {"status": "unexpected_error"}
        exit_code = EXIT_TASK_FAILED
    _print_result(result)
    return exit_code


def _print_result(result: dict[str, Any]) -> None:
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
