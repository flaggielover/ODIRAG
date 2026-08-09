#!/usr/bin/env python3
"""Verify the live evidence gate without exposing credentials or provider payloads."""

from __future__ import annotations

import argparse
import json
import os
import sys
from decimal import Decimal
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SUPPORTED_QUERY = (
    "存量APP备案阶段是什么时间？"
    "已完成网站备案手续的APP是否需要重复填报主办者真实身份信息？"
)
INSUFFICIENT_QUERY = "火星地表是否已经发现活体恐龙？"
ADVERSARIAL_QUERIES = (
    "为什么取消APP备案？",
    "APP备案罚款金额是多少？",
    "APP备案是否适用于微信小程序？",
)


class AcceptanceError(RuntimeError):
    pass


class ApiClient:
    def __init__(self, base_url: str, *, token: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode()
            if payload is not None
            else None
        )
        headers = {"Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            headers=headers,
            method=method,
        )
        try:
            with urlopen(request, timeout=120) as response:
                result = json.loads(response.read().decode())
        except HTTPError as exc:
            raise AcceptanceError(f"api_http_{exc.code}") from None
        except (URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AcceptanceError("api_unavailable_or_invalid") from exc
        if not isinstance(result, dict):
            raise AcceptanceError("api_response_is_not_an_object")
        return result


def _require(condition: object, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def _tokens(payload: object) -> int:
    if not isinstance(payload, dict):
        return 0
    for key in ("total_tokens", "tokens", "token_count"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    return sum(
        value
        for value in (payload.get("prompt_tokens"), payload.get("completion_tokens"))
        if isinstance(value, int) and not isinstance(value, bool) and value > 0
    )


def _login(base_url: str, username: str, password: str) -> ApiClient:
    anonymous = ApiClient(base_url)
    response = anonymous.request(
        "POST",
        "/auth/login",
        {"username": username, "password": password},
    )
    token = response.get("access_token")
    _require(isinstance(token, str) and token, "authentication_failed")
    return ApiClient(base_url, token=str(token))


def _validate_supported(api: ApiClient) -> dict[str, Any]:
    answer = api.request("POST", "/chat", {"query": SUPPORTED_QUERY})
    trace = api.request("GET", f"/chat/traces/{answer.get('trace_id', '')}")
    evidence = answer.get("evidence_sufficiency")
    citations = answer.get("citations")
    stored_evidence = trace.get("evidence_decision_json")
    _require(answer.get("refusal") is False, "supported_query_was_refused")
    _require(
        isinstance(evidence, dict) and evidence.get("sufficient") is True, "gate_failed"
    )
    _require(
        isinstance(citations, list) and citations, "supported_answer_has_no_citations"
    )
    _require(isinstance(stored_evidence, dict), "evidence_decision_not_persisted")
    _require(
        stored_evidence.get("answer_support_validated") is True, "answer_not_validated"
    )
    _require(_tokens(trace.get("token_usage_json")) > 0, "direct_llm_not_observed")
    supported_ids = set(evidence.get("supported_chunk_ids") or [])
    citation_ids = {
        str(item.get("chunk_id")) for item in citations if isinstance(item, dict)
    }
    _require(
        citation_ids and citation_ids.issubset(supported_ids),
        "citation_not_gate_supported",
    )
    first = citations[0]
    _require(isinstance(first, dict), "citation_is_invalid")
    _require(
        first.get("title") and first.get("url") and first.get("chunk_id"),
        "citation_incomplete",
    )
    return {
        "trace_id": answer.get("trace_id"),
        "model": trace.get("model_name"),
        "retrieval_hits": len(trace.get("final_context_json") or []),
        "supported_chunks": len(supported_ids),
        "answer": answer.get("answer"),
        "citation_count": len(citations),
        "citation": {
            "title": first.get("title"),
            "source_url": first.get("url"),
            "chunk_id": first.get("chunk_id"),
        },
        "tokens": _tokens(trace.get("token_usage_json")),
    }


def _validate_insufficient(api: ApiClient) -> dict[str, Any]:
    answer = api.request("POST", "/chat", {"query": INSUFFICIENT_QUERY})
    trace = api.request("GET", f"/chat/traces/{answer.get('trace_id', '')}")
    evidence = answer.get("evidence_sufficiency")
    stored_evidence = trace.get("evidence_decision_json")
    candidates = len(trace.get("final_context_json") or [])
    _require(candidates > 0, "regression_query_did_not_retrieve_candidates")
    _require(answer.get("refusal") is True, "insufficient_query_was_answered")
    _require(answer.get("citations") == [], "refusal_retained_citations")
    _require(
        isinstance(evidence, dict) and evidence.get("sufficient") is False,
        "gate_passed",
    )
    _require(isinstance(stored_evidence, dict), "evidence_decision_not_persisted")
    _require(
        _tokens(trace.get("token_usage_json")) == 0, "answer_llm_was_called_for_refusal"
    )
    _require(Decimal(str(trace.get("cost", 0))) == 0, "refusal_incurred_llm_cost")
    return {
        "trace_id": answer.get("trace_id"),
        "retrieval_candidates": candidates,
        "reason": evidence.get("reason"),
        "confidence": evidence.get("confidence"),
        "citation_count": 0,
        "llm_tokens": 0,
        "refusal": True,
    }


def _validate_adversarial(api: ApiClient) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for query in ADVERSARIAL_QUERIES:
        answer = api.request("POST", "/chat", {"query": query})
        trace = api.request("GET", f"/chat/traces/{answer.get('trace_id', '')}")
        evidence = answer.get("evidence_sufficiency")
        candidates = len(trace.get("final_context_json") or [])
        _require(
            candidates > 0,
            f"adversarial_query_did_not_retrieve_candidates:{query}",
        )
        _require(
            answer.get("refusal") is True,
            f"adversarial_query_was_answered:{query}",
        )
        _require(
            answer.get("citations") == [],
            f"adversarial_refusal_retained_citations:{query}",
        )
        _require(
            isinstance(evidence, dict) and evidence.get("sufficient") is False,
            f"adversarial_query_passed_gate:{query}",
        )
        _require(
            _tokens(trace.get("token_usage_json")) == 0,
            f"adversarial_query_called_answer_llm:{query}",
        )
        _require(
            Decimal(str(trace.get("cost", 0))) == 0,
            f"adversarial_query_incurred_cost:{query}",
        )
        results.append(
            {
                "query": query,
                "trace_id": answer.get("trace_id"),
                "retrieval_candidates": candidates,
                "reason": evidence.get("reason"),
                "confidence": evidence.get("confidence"),
                "refusal": True,
            }
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api")
    args = parser.parse_args()
    username = os.getenv("ODIRAG_ADMIN_USERNAME", "admin")
    password = os.getenv("ODIRAG_ADMIN_PASSWORD")
    if not password:
        print(
            json.dumps({"status": "BLOCKED", "reason": "ODIRAG_ADMIN_PASSWORD missing"})
        )
        return 2
    try:
        api = _login(args.base_url, username, password)
        result = {
            "status": "PASS-LIVE",
            "supported": _validate_supported(api),
            "insufficient": _validate_insufficient(api),
            "adversarial": _validate_adversarial(api),
        }
    except AcceptanceError as exc:
        print(
            json.dumps({"status": "FAIL-LIVE", "reason": str(exc)}, ensure_ascii=False)
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
