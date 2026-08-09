from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


def _load_script() -> ModuleType:
    path = Path(__file__).parents[3] / "scripts" / "live_accept_coze_batch.py"
    spec = importlib.util.spec_from_file_location("live_accept_coze_batch", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()


class FakeApi:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []

    def request_json(self, method: str, path: str, payload: dict[str, Any] | None = None) -> Any:
        self.calls.append((method, path, payload))
        return self.responses.pop(0)


def _configured() -> dict[str, Any]:
    return {
        "enabled": True,
        "token_configured": True,
        "legacy_workflow_configured": True,
        "batch_workflow_configured": True,
        "default_contract": "batch_crawl",
    }


def test_missing_batch_deployment_is_explicit_and_does_not_create_task() -> None:
    api = FakeApi([{**_configured(), "batch_workflow_configured": False}])

    exit_code, result = SCRIPT.run_acceptance(
        api,
        source_column_id=7,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert exit_code == SCRIPT.EXIT_NOT_PUBLISHED
    assert result == {"status": "batch_workflow_not_published"}
    assert api.calls == [("GET", "/system/coze/status", None)]


def test_success_queues_bounded_batch_and_reports_persisted_counts() -> None:
    api = FakeApi(
        [
            _configured(),
            {"id": 41, "status": "queued", "current_stage": "queued"},
            {
                "id": 41,
                "status": "completed",
                "current_stage": "completed",
                "accepted_count": 2,
                "rejected_count": 1,
                "pending_review_count": 0,
                "failed_count": 0,
                "discovered_count": 3,
                "fetched_count": 3,
                "provider_error_code": None,
            },
            [
                {
                    "contract": "batch_crawl",
                    "status": "completed",
                    "http_status_code": 200,
                }
            ],
            {
                "crawl_task_id": 41,
                "database_document_count": 2,
                "chunk_count": 6,
                "qdrant_collection_exists": True,
                "qdrant_point_count": 6,
            },
        ]
    )

    exit_code, result = SCRIPT.run_acceptance(
        api,
        source_column_id=7,
        timeout_seconds=1,
        poll_interval_seconds=0,
        sleep=lambda _seconds: None,
    )

    assert exit_code == SCRIPT.EXIT_OK
    assert result["status"] == "live_batch_verified"
    assert result["accepted_count"] == 2
    assert result["rejected_count"] == 1
    create_payload = api.calls[1][2]
    assert create_payload is not None
    assert create_payload["execution_mode"] == "queued"
    assert create_payload["provider"] == "coze"
    assert create_payload["contract_mode"] == "batch_crawl"
    assert create_payload["provider_contract"] == "batch_crawl"
    assert create_payload["max_articles"] == 5
    assert create_payload["max_pages"] == 1


def test_task_level_not_published_error_maps_to_stable_status() -> None:
    api = FakeApi(
        [
            _configured(),
            {
                "id": 55,
                "status": "failed",
                "provider_error_code": "COZE_BATCH_WORKFLOW_NOT_PUBLISHED",
            },
        ]
    )

    exit_code, result = SCRIPT.run_acceptance(
        api,
        source_column_id=8,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert exit_code == SCRIPT.EXIT_NOT_PUBLISHED
    assert result == {"status": "batch_workflow_not_published", "task_id": 55}


def test_output_summary_contains_no_credentials_or_raw_response() -> None:
    api = FakeApi(
        [
            _configured(),
            {
                "id": 63,
                "status": "partial_failed",
                "current_stage": "partial_failed",
                "accepted_count": 1,
                "rejected_count": 0,
                "pending_review_count": 1,
                "failed_count": 1,
                "discovered_count": 3,
                "fetched_count": 2,
                "provider_error_code": None,
            },
            [
                {
                    "contract": "batch_crawl",
                    "status": "completed",
                    "http_status_code": 200,
                    "request_json": {"api_token": "must-not-appear"},
                    "raw_response_json": {"secret": "must-not-appear"},
                }
            ],
            {
                "crawl_task_id": 63,
                "database_document_count": 1,
                "chunk_count": 2,
                "qdrant_collection_exists": True,
                "qdrant_point_count": 2,
            },
        ]
    )

    exit_code, result = SCRIPT.run_acceptance(
        api,
        source_column_id=9,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert exit_code == SCRIPT.EXIT_OK
    rendered = str(result)
    assert "must-not-appear" not in rendered
    assert "request_json" not in rendered
    assert "raw_response_json" not in rendered


def test_completed_invocation_with_empty_result_fails_acceptance() -> None:
    api = FakeApi(
        [
            _configured(),
            {
                "id": 71,
                "status": "completed",
                "current_stage": "completed",
                "accepted_count": 0,
                "rejected_count": 0,
                "pending_review_count": 0,
                "failed_count": 0,
                "discovered_count": 0,
                "fetched_count": 0,
                "provider_error_code": None,
            },
            [
                {
                    "contract": "batch_crawl",
                    "status": "completed",
                    "http_status_code": 200,
                }
            ],
            {
                "crawl_task_id": 71,
                "database_document_count": 0,
                "chunk_count": 0,
                "qdrant_collection_exists": False,
                "qdrant_point_count": 0,
            },
        ]
    )

    exit_code, result = SCRIPT.run_acceptance(
        api,
        source_column_id=10,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert exit_code == SCRIPT.EXIT_TASK_FAILED
    assert result["status"] == "batch_result_empty"
    assert result["batch_invocation_count"] == 1
