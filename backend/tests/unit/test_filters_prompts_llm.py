from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from app.filters import FilterDecision, RuleFilter
from app.llm import CozeAdapter, DirectLLMAdapter
from app.providers import ProviderResponseError
from app.repositories.reviews import ReviewRepository
from app.services.filter_config import load_filter_config
from app.services.prompts import PromptService


def test_filter_config_and_decisions() -> None:
    rule_filter = RuleFilter(
        load_filter_config(__import__("pathlib").Path("../config/filters.yaml"))
    )
    rejected = rule_filter.evaluate(title="Policy", content="short", official_source=True)
    assert rejected.decision is FilterDecision.REJECT
    accepted = rule_filter.evaluate(
        title="Software policy notice",
        content="policy support and application requirements " * 10,
        official_source=True,
    )
    assert accepted.decision is FilterDecision.ACCEPT


async def test_direct_llm_adapter_validates_json_and_retains_raw_response() -> None:
    raw = (
        '{"decision":"approve","quality_score":0.9,"document_type":"notice",'
        '"topics":["software"],"summary":"ok","reasons":[],"extracted_fields":{}}'
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": raw}}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://llm.test/v1",
            api_key="secret",
            model_name="test-model",
            client=client,
        )
        result = await adapter.review_document(title="title", content="body", prompt="prompt")
    assert result.decision == "approve"
    assert result.raw_response == raw


async def test_direct_llm_answer_injects_schema_and_accepts_valid_openai_response() -> None:
    captured_request: dict[str, object] = {}
    raw = json.dumps(
        {
            "answer": "The notice lists three attachments.",
            "cited_chunk_ids": ["chunk-1"],
            "refusal": False,
            "refusal_reason": None,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        captured_request.update(json.loads(request.content))
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "chatcmpl-live-shape",
                "object": "chat.completion",
                "created": 1_722_000_000,
                "model": "gpt-4.1-mini-2025-04-14",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": raw},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 40,
                    "completion_tokens": 20,
                    "total_tokens": 60,
                },
                "system_fingerprint": "fp_test",
            },
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://api.openai.com/v1",
            api_key="secret",
            model_name="gpt-4.1-mini",
            client=client,
        )
        result = await adapter.generate_answer(
            query="Which attachments are listed?",
            context=[{"chunk_id": "chunk-1", "content": "Three attachments are listed."}],
            prompt="Use only the supplied evidence.",
        )

    assert result.answer == "The notice lists three attachments."
    assert result.cited_chunk_ids == ["chunk-1"]
    assert result.token_usage == {
        "prompt_tokens": 40,
        "completion_tokens": 20,
        "total_tokens": 60,
    }
    assert captured_request["response_format"] == {"type": "json_object"}
    system_message = captured_request["messages"][0]["content"]  # type: ignore[index]
    assert "Use only the supplied evidence." in system_message
    assert '"title":"AnswerResult"' in system_message
    assert '"cited_chunk_ids"' in system_message
    assert "attachments" in system_message
    assert "retrieval context" in system_message
    assert '"token_usage"' not in system_message
    assert '"cost"' not in system_message


@pytest.mark.parametrize(
    ("raw", "error_match"),
    [
        (
            '{"answer":"Supported answer","cited_chunk_ids":["chunk-1"],'
            '"attachments":["one"],"source":["chunk-1"],"refusal":false}',
            "attachments",
        ),
        (
            '{"cited_chunk_ids":["chunk-1"],"refusal":false}',
            "answer",
        ),
        (
            '{"answer":"Supported answer","refusal":false}',
            "cited_chunk_ids",
        ),
        (
            '{"answer":"   ","cited_chunk_ids":["chunk-1"],"refusal":false}',
            "non-empty",
        ),
        (
            '{"answer":"Supported answer","cited_chunk_ids":[],"refusal":false}',
            "must not be empty",
        ),
        (
            '{"answer":"Insufficient evidence","cited_chunk_ids":["chunk-1"],'
            '"refusal":true,"refusal_reason":"insufficient_evidence"}',
            "must be empty for a refusal",
        ),
        (
            '{"answer":"Insufficient evidence","cited_chunk_ids":[],"refusal":true}',
            "refusal_reason must be non-empty",
        ),
        (
            '{"answer":"Supported answer","cited_chunk_ids":["chunk-1"],'
            '"refusal":false,"refusal_reason":"not_applicable"}',
            "refusal_reason must be null",
        ),
        (
            '{"answer":"Supported answer","cited_chunk_ids":["not-retrieved"]}',
            "retrieval context",
        ),
        (
            "not valid JSON",
            "invalid",
        ),
    ],
)
async def test_direct_llm_answer_rejects_invalid_structured_responses(
    raw: str,
    error_match: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": raw}}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://api.openai.com/v1",
            api_key="secret",
            model_name="gpt-4.1-mini",
            client=client,
        )
        with pytest.raises(ProviderResponseError, match=error_match):
            await adapter.generate_answer(
                query="question",
                context=[{"chunk_id": "chunk-1", "content": "evidence"}],
                prompt="Use evidence.",
            )


async def test_direct_llm_answer_accepts_evidence_refusal_contract() -> None:
    raw = json.dumps(
        {
            "answer": "The retrieved evidence is insufficient.",
            "cited_chunk_ids": [],
            "refusal": True,
            "refusal_reason": "insufficient_evidence",
        }
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={"choices": [{"message": {"content": raw}}]},
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://api.openai.com/v1",
            api_key="secret",
            model_name="gpt-4.1-mini",
            client=client,
        )
        result = await adapter.generate_answer(
            query="unsupported question",
            context=[{"chunk_id": "chunk-1", "content": "unrelated evidence"}],
            prompt="Use evidence.",
        )

    assert result.refusal is True
    assert result.refusal_reason == "insufficient_evidence"
    assert result.cited_chunk_ids == []


async def test_direct_llm_adapter_preserves_provider_usage_and_cost() -> None:
    raw = '{"decision":"approve","quality_score":0.9,"extracted_fields":{}}'
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": raw}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8},
                "cost": "0.0007",
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://llm.test/v1",
            api_key="secret",
            model_name="test-model",
            client=client,
        )
        result = await adapter.review_document(title="title", content="body", prompt="prompt")
    assert result.token_usage == {
        "prompt_tokens": 12,
        "completion_tokens": 8,
        "total_tokens": 20,
    }
    assert result.cost == Decimal("0.0007")


@pytest.mark.parametrize(
    "provider_cost",
    ["NaN", "sNaN", "Infinity", "-Infinity", "-0.1", "10000000000"],
)
async def test_direct_llm_adapter_rejects_unstorable_provider_cost(
    provider_cost: str,
) -> None:
    raw = '{"decision":"approve","quality_score":0.9,"extracted_fields":{}}'
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": raw}}],
                "cost": provider_cost,
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://llm.test/v1",
            api_key="secret",
            model_name="test-model",
            client=client,
        )
        result = await adapter.review_document(title="title", content="body", prompt="prompt")
    assert result.cost is None


async def test_direct_llm_adapter_quantizes_provider_cost_to_database_scale() -> None:
    raw = '{"decision":"approve","quality_score":0.9,"extracted_fields":{}}'
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={
                "choices": [{"message": {"content": raw}}],
                "cost": "0.123456789",
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = DirectLLMAdapter(
            base_url="https://llm.test/v1",
            api_key="secret",
            model_name="test-model",
            client=client,
        )
        result = await adapter.review_document(title="title", content="body", prompt="prompt")
    assert result.cost == Decimal("0.12345679")


async def test_coze_adapter_preserves_nested_usage_and_cost() -> None:
    raw = '{"answer":"基于证据的回答","cited_chunk_ids":["chunk-1"]}'
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            request=request,
            json={
                "data": {
                    "messages": [{"role": "assistant", "content": raw}],
                    "usage": {"input_tokens": 3, "output_tokens": 4, "cost": "0.001"},
                }
            },
        )
    )
    async with httpx.AsyncClient(transport=transport) as client:
        adapter = CozeAdapter(
            base_url="https://coze.test",
            api_token="secret",
            bot_id="bot",
            client=client,
        )
        result = await adapter.generate_answer(query="q", context=[], prompt="p")
    assert result.token_usage == {
        "prompt_tokens": 3,
        "completion_tokens": 4,
        "total_tokens": 7,
    }
    assert result.cost == Decimal("0.001")


async def test_prompt_version_content_is_immutable(app) -> None:
    async with app.state.database.session_factory() as session:
        service = PromptService(ReviewRepository(session))
        await service.ensure(name="test_prompt", version="v1", content="first")
        with pytest.raises(ValueError, match="does not match"):
            await service.ensure(name="test_prompt", version="v1", content="changed")
