from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.coze import (
    BatchArticle,
    BatchAttachment,
    BatchCrawlRequest,
    BatchCrawlResponse,
    BatchFailedUrl,
    BatchSource,
    BatchStatistics,
)

CASES_DIR = Path(__file__).parents[3] / "docs" / "coze_batch_test_cases"


def test_all_coze_case_files_are_utf8_json() -> None:
    files = sorted(CASES_DIR.glob("*.json"))
    assert files
    for path in files:
        json.loads(path.read_text(encoding="utf-8"))


def test_documented_json_schema_fields_match_backend_models() -> None:
    schema = json.loads((CASES_DIR / "batch_crawl_result.schema.json").read_text(encoding="utf-8"))
    definitions = schema["$defs"]

    assert set(schema["properties"]) == set(BatchCrawlResponse.model_fields)
    assert set(schema["properties"]["source"]["properties"]) == set(BatchSource.model_fields)
    assert set(schema["properties"]["statistics"]["properties"]) == set(
        BatchStatistics.model_fields
    )
    assert set(definitions["article"]["properties"]) == set(BatchArticle.model_fields)
    assert set(definitions["attachment"]["properties"]) == set(BatchAttachment.model_fields)
    assert set(definitions["failedUrl"]["properties"]) == set(BatchFailedUrl.model_fields)


@pytest.mark.parametrize("path", sorted(CASES_DIR.glob("sample_*_response.json")))
def test_coze_response_samples_match_strict_backend_contract(path: Path) -> None:
    BatchCrawlResponse.model_validate_json(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", sorted(CASES_DIR.glob("0[1-9]_*.json")))
def test_valid_coze_inputs_match_strict_backend_contract(path: Path) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    BatchCrawlRequest.model_validate(payload["input"])


def test_invalid_url_case_is_rejected_before_external_request() -> None:
    payload = json.loads((CASES_DIR / "10_invalid_url.json").read_text(encoding="utf-8"))
    with pytest.raises(ValidationError):
        BatchCrawlRequest.model_validate(payload["input"])


def test_batch_task_id_is_a_strict_non_empty_string() -> None:
    request_payload = json.loads((CASES_DIR / "01_minimal_valid.json").read_text(encoding="utf-8"))[
        "input"
    ]
    response_payload = json.loads(
        (CASES_DIR / "sample_success_response.json").read_text(encoding="utf-8")
    )

    BatchCrawlRequest.model_validate(request_payload)
    BatchCrawlResponse.model_validate(response_payload)

    for invalid in (1, ""):
        with pytest.raises(ValidationError):
            BatchCrawlRequest.model_validate({**request_payload, "task_id": invalid})
        with pytest.raises(ValidationError):
            BatchCrawlResponse.model_validate({**response_payload, "task_id": invalid})
