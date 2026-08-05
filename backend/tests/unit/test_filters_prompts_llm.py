from __future__ import annotations

from decimal import Decimal

import httpx
import pytest

from app.filters import FilterDecision, RuleFilter
from app.llm import CozeAdapter, DirectLLMAdapter
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
