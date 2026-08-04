from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.protocols import AnswerResult, EvidenceCheck, QueryPlan, ReviewResult
from app.providers import ProviderResponseError, ProviderUnavailableError

ResultT = TypeVar("ResultT", bound=BaseModel)


class DirectLLMAdapter:
    """OpenAI-compatible chat completion adapter with strict JSON validation."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model_name: str,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def review_document(self, *, title: str, content: str, prompt: str) -> ReviewResult:
        return await self._structured(prompt, {"title": title, "content": content}, ReviewResult)

    async def analyze_query(self, *, query: str, prompt: str) -> QueryPlan:
        return await self._structured(prompt, {"query": query}, QueryPlan)

    async def generate_answer(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> AnswerResult:
        return await self._structured(prompt, {"query": query, "context": context}, AnswerResult)

    async def check_evidence(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> EvidenceCheck:
        return await self._structured(prompt, {"query": query, "context": context}, EvidenceCheck)

    async def _structured(
        self, prompt: str, payload: Mapping[str, Any], result_type: type[ResultT]
    ) -> ResultT:
        if not self.api_key:
            raise ProviderUnavailableError("direct_llm", "API key is not configured")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": prompt},
                        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                    ],
                },
            )
            response.raise_for_status()
            response_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("direct_llm", str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            content = response_payload["choices"][0]["message"]["content"]
            result = result_type.model_validate_json(content)
            if isinstance(result, ReviewResult):
                result.raw_response = content
            return result
        except (KeyError, IndexError, TypeError, ValidationError) as exc:
            raise ProviderResponseError("direct_llm", str(exc)) from exc


class CozeAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str | None,
        bot_id: str | None,
        model_name: str = "coze-bot",
        timeout_seconds: float = 90.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.bot_id = bot_id
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self._client = client

    async def review_document(self, *, title: str, content: str, prompt: str) -> ReviewResult:
        return await self._invoke(
            "review_document", {"title": title, "content": content, "prompt": prompt}, ReviewResult
        )

    async def analyze_query(self, *, query: str, prompt: str) -> QueryPlan:
        return await self._invoke("analyze_query", {"query": query, "prompt": prompt}, QueryPlan)

    async def generate_answer(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> AnswerResult:
        return await self._invoke(
            "generate_answer", {"query": query, "context": context, "prompt": prompt}, AnswerResult
        )

    async def check_evidence(
        self, *, query: str, context: list[dict[str, Any]], prompt: str
    ) -> EvidenceCheck:
        return await self._invoke(
            "check_evidence", {"query": query, "context": context, "prompt": prompt}, EvidenceCheck
        )

    async def _invoke(
        self, action: str, payload: dict[str, Any], result_type: type[ResultT]
    ) -> ResultT:
        if not self.api_token or not self.bot_id:
            raise ProviderUnavailableError("coze", "API token and bot ID are required")
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self.timeout_seconds)
        try:
            response = await client.post(
                f"{self.base_url}/v3/chat",
                headers={"Authorization": f"Bearer {self.api_token}"},
                json={
                    "bot_id": self.bot_id,
                    "user_id": "odirag-service",
                    "stream": False,
                    "additional_messages": [
                        {
                            "role": "user",
                            "content": json.dumps(
                                {"action": action, **payload}, ensure_ascii=False
                            ),
                            "content_type": "text",
                        }
                    ],
                },
            )
            response.raise_for_status()
            response_payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ProviderUnavailableError("coze", str(exc)) from exc
        finally:
            if owns_client:
                await client.aclose()
        try:
            content = _coze_content(response_payload)
            result = result_type.model_validate_json(content)
            if isinstance(result, ReviewResult):
                result.raw_response = content
            return result
        except (KeyError, TypeError, ValidationError, ValueError) as exc:
            raise ProviderResponseError("coze", str(exc)) from exc


def _coze_content(payload: dict[str, Any]) -> str:
    messages = payload.get("data", {}).get("messages") or payload.get("messages") or []
    for message in reversed(messages):
        if message.get("type") == "answer" or message.get("role") == "assistant":
            return str(message["content"])
    raise ValueError("answer message is missing")
