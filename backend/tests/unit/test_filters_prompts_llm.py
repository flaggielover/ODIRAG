from __future__ import annotations

import httpx
import pytest

from app.filters import FilterDecision, RuleFilter
from app.llm import DirectLLMAdapter
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


async def test_prompt_version_content_is_immutable(app) -> None:
    async with app.state.database.session_factory() as session:
        service = PromptService(ReviewRepository(session))
        await service.ensure(name="test_prompt", version="v1", content="first")
        with pytest.raises(ValueError, match="does not match"):
            await service.ensure(name="test_prompt", version="v1", content="changed")
