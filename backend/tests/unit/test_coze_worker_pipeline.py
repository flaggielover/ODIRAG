from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from app.config import Settings
from app.crawler.providers import (
    CrawlContract,
    CrawlProviderConnection,
    CrawlProviderError,
    CrawlProviderResult,
)
from app.models import (
    CozeInvocation,
    CrawlTask,
    CrawlTaskFailure,
    DataLineage,
    Document,
    DocumentReview,
    DocumentVersion,
    Source,
    SourceColumn,
)
from app.repositories.crawl import CrawlRepository
from app.schemas.coze import BatchCrawlResponse, parse_batch_crawl_response
from app.services.crawl import CrawlService


class UnusedFetcher:
    async def fetch(self, _url: str) -> Any:
        raise AssertionError("local fetcher must not run for a Coze task")


class NormalizationCrash(BaseException):
    """Simulate a process-level normalization crash after raw persistence."""


class FixtureProvider:
    def __init__(self, raw: dict[str, Any], *, crash_on_normalize: bool = False) -> None:
        self.raw = raw
        self.crash_on_normalize = crash_on_normalize

    async def start_crawl(
        self, payload: Mapping[str, Any], *, contract: CrawlContract | None = None
    ) -> CrawlProviderResult:
        assert payload["task_id"]
        assert isinstance(payload["task_id"], str)
        assert contract == "batch_crawl"
        return CrawlProviderResult(
            contract="batch_crawl",
            status="completed",
            status_code=200,
            attempts=1,
            duration_ms=12,
            raw_response=self.raw,
        )

    def normalize_result(
        self, payload: Any, *, contract: CrawlContract
    ) -> tuple[dict[str, Any], BatchCrawlResponse | None]:
        assert contract == "batch_crawl"
        if self.crash_on_normalize:
            raise NormalizationCrash
        batch, _raw = parse_batch_crawl_response(payload)
        return batch.model_dump(mode="json"), batch

    async def test_connection(
        self, *, contract: CrawlContract | None = None, source_url: str | None = None
    ) -> CrawlProviderConnection:
        return CrawlProviderConnection(True, contract or "batch_crawl", 200, 1)

    async def get_task_status(self, provider_task_id: str) -> CrawlProviderResult:
        raise AssertionError(f"unexpected status lookup: {provider_task_id}")

    async def cancel_task(self, provider_task_id: str) -> bool:
        return False


def _settings(base: Settings) -> Settings:
    return base.model_copy(
        update={
            "coze_enabled": True,
            "coze_api_token": SecretStr("fixture-secret"),
            "coze_batch_api_url": "https://batch.example/run",
            "coze_default_contract": "batch_crawl",
        }
    )


async def _seed_task(session) -> int:
    source = Source(
        source_key=f"worker-{uuid.uuid4().hex}",
        name="四川省软件行业协会",
        domain="example.com",
        region="四川省",
        homepage_url="https://example.com/",
        crawl_provider="coze",
        coze_contract_mode="batch_crawl",
    )
    column = SourceColumn(
        source=source,
        column_key="news",
        column_name="行业动态",
        column_url="https://example.com/news",
        request_interval_seconds=0,
    )
    task = CrawlTask(
        source_column=column,
        status="pending",
        crawl_provider="coze",
        provider="coze",
        provider_contract="batch_crawl",
        contract_mode="batch_crawl",
        current_stage="pending",
    )
    session.add_all([source, column, task])
    await session.commit()
    return task.id


async def _seed_followup_task(session, source_column_id: int) -> int:
    task = CrawlTask(
        source_column_id=source_column_id,
        status="pending",
        crawl_provider="coze",
        provider="coze",
        provider_contract="batch_crawl",
        contract_mode="batch_crawl",
        current_stage="pending",
    )
    session.add(task)
    await session.commit()
    return task.id


def _article(title: str, suffix: str) -> dict[str, Any]:
    content = f"{title}的中文正文"
    return {
        "title": title,
        "url": f"https://example.com/news/{suffix}",
        "published_at": "2026-08-04",
        "organization": "四川省软件行业协会",
        "region": "四川省",
        "column_name": "行业动态",
        "content": content,
        "content_length": len(content),
        "attachments": [],
        "extraction_method": "html",
        "needs_ocr": False,
        "image_urls": [],
        "image_count": 0,
        "image_alt_texts": [],
        "decision": "accepted",
        "accepted": True,
        "quality_score": 90,
        "decision_reason": "内容完整",
        "warnings": [],
    }


def _batch_response(task_id: int | str, articles: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "success": True,
        "task_id": str(task_id),
        "source": {
            "source_url": "https://example.com/news",
            "source_name": "四川省软件行业协会",
            "region": "四川省",
            "column_name": "行业动态",
        },
        "statistics": {
            "pages_visited": 1,
            "articles_discovered": len(articles),
            "articles_fetched": len(articles),
            "articles_accepted": len(articles),
            "articles_rejected": 0,
            "articles_pending_review": 0,
            "articles_failed": 0,
        },
        "articles": articles,
        "failed_urls": [],
        "warnings": [],
    }


async def test_raw_response_survives_normalization_process_crash(app, test_settings) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response(task_id, [_article("中文标题", "one")])
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw, crash_on_normalize=True),
        )

        with pytest.raises(NormalizationCrash):
            await service.execute(task_id)

    async with app.state.database.session_factory() as verification_session:
        invocation = await verification_session.scalar(
            select(CozeInvocation).where(CozeInvocation.crawl_task_id == task_id)
        )
        assert invocation is not None
        assert invocation.status == "response_received"
        assert invocation.raw_response_json == raw
        assert invocation.normalized_response_json is None


async def test_mark_queued_does_not_overwrite_a_fast_worker_claim(app, test_settings) -> None:
    async with app.state.database.session_factory() as api_session:
        task_id = await _seed_task(api_session)
        api_service = CrawlService(
            CrawlRepository(api_session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider({}),
        )

        async with app.state.database.session_factory() as worker_session:
            claimed = await CrawlRepository(worker_session).claim_task(task_id)
            assert claimed is not None
            assert claimed.status == "running"

        result = await api_service.mark_queued(task_id)

        assert result.status == "running"
        assert result.current_stage == "running"


async def test_one_document_save_failure_keeps_other_articles(
    app, test_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response(
            task_id,
            [_article("第一篇中文标题", "one"), _article("第二篇中文标题", "two")],
        )
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw),
        )
        original_save = service._save_coze_article

        async def fail_second(task: CrawlTask, column: object, article: object) -> None:
            if getattr(article, "title", "") == "第二篇中文标题":
                raise ValueError("fixture document failure")
            await original_save(task, column, article)

        monkeypatch.setattr(service, "_save_coze_article", fail_second)
        result = await service.execute(task_id)

        assert result.status == "partial_failed"
        assert result.accepted_count == 1
        assert result.failed_count == 1
        assert await session.scalar(select(func.count(Document.id))) == 1
        source = await session.scalar(select(Source))
        assert source is not None
        assert source.last_crawl_time is not None
        assert source.last_successful_crawl_at is None
        assert source.last_coze_error == "COZE_PARTIAL_FAILED"
        failure = await session.scalar(
            select(CrawlTaskFailure).where(CrawlTaskFailure.crawl_task_id == task_id)
        )
        assert failure is not None
        assert failure.url.endswith("/two")
        assert failure.error_code == "COZE_DOCUMENT_SAVE_FAILED"
        assert failure.retryable is True


async def test_ocr_recrawl_refreshes_document_and_identical_repeat_is_idempotent(
    app, test_settings
) -> None:
    async with app.state.database.session_factory() as session:
        first_task_id = await _seed_task(session)
        failed_ocr = _article("OCR notice", "ocr-notice")
        failed_ocr.update(
            {
                "content": "",
                "content_length": 0,
                "extraction_method": "image",
                "needs_ocr": True,
                "image_urls": ["https://example.com/images/ocr-notice.png"],
                "image_count": 1,
                "decision": "rejected",
                "accepted": False,
                "quality_score": 0,
                "decision_reason": "OCR failed",
                "warnings": ["OCR_FAILED"],
            }
        )
        first_raw = _batch_response(first_task_id, [failed_ocr])
        first_raw["statistics"].update({"articles_accepted": 0, "articles_rejected": 1})
        first_service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(first_raw),
        )

        first_result = await first_service.execute(first_task_id)

        assert first_result.status == "completed"
        document = await session.scalar(select(Document))
        assert document is not None
        assert document.content == ""
        assert document.final_status == "rejected"
        source_column_id = document.source_column_id
        assert source_column_id is not None

        second_task_id = await _seed_followup_task(session, source_column_id)
        recovered_ocr = _article("OCR notice", "ocr-notice")
        recovered_content = "OCR recovered official notice content with enough evidence."
        recovered_ocr.update(
            {
                "content": recovered_content,
                "content_length": len(recovered_content),
                "extraction_method": "image_ocr",
                "needs_ocr": False,
                "image_urls": ["https://example.com/images/ocr-notice.png"],
                "image_count": 1,
                "decision_reason": "OCR content passed quality review",
                "warnings": ["ocr_performed"],
            }
        )
        second_service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(_batch_response(second_task_id, [recovered_ocr])),
        )

        second_result = await second_service.execute(second_task_id)

        await session.refresh(document)
        assert second_result.status == "waiting_review"
        assert second_result.url_duplicate_count == 1
        assert second_result.pending_review_count == 1
        assert document.content == recovered_content
        assert document.version == 2
        assert document.llm_review_status == "accepted"
        assert document.manual_review_status == "pending"
        assert document.final_status == "pending_manual_review"
        assert document.index_status == "stale"
        assert await session.scalar(select(func.count(Document.id))) == 1
        assert await session.scalar(select(func.count(DocumentVersion.id))) == 2
        assert await session.scalar(select(func.count(DocumentReview.id))) == 2
        latest_review = await session.scalar(
            select(DocumentReview).order_by(DocumentReview.id.desc()).limit(1)
        )
        assert latest_review is not None
        assert latest_review.extracted_fields_json["extraction_method"] == "image_ocr"
        assert latest_review.extracted_fields_json["needs_ocr"] is False
        assert (
            await session.scalar(
                select(func.count(DataLineage.id)).where(
                    DataLineage.crawl_task_id == second_task_id,
                    DataLineage.document_version_id.is_not(None),
                )
            )
            == 1
        )

        document.manual_review_status = "approve"
        document.final_status = "approved"
        await session.commit()
        third_task_id = await _seed_followup_task(session, source_column_id)
        third_service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(_batch_response(third_task_id, [recovered_ocr])),
        )

        third_result = await third_service.execute(third_task_id)

        await session.refresh(document)
        assert third_result.status == "completed"
        assert third_result.url_duplicate_count == 1
        assert third_result.pending_review_count == 0
        assert document.version == 2
        assert document.manual_review_status == "approve"
        assert document.final_status == "approved"
        assert await session.scalar(select(func.count(DocumentVersion.id))) == 2
        assert await session.scalar(select(func.count(DocumentReview.id))) == 2


@pytest.mark.parametrize(
    ("success", "warnings"),
    [(False, ["NO_ARTICLES"]), (True, [])],
)
async def test_no_articles_batch_uses_distinct_completed_state(
    app, test_settings, success: bool, warnings: list[str]
) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response(task_id, [])
        raw["success"] = success
        raw["warnings"] = warnings
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw),
        )

        result = await service.execute(task_id)

        assert result.status == "completed"
        assert result.provider_status == "no_articles"
        assert result.discovered_count == 0
        source = await session.scalar(select(Source))
        assert source is not None
        assert source.last_crawl_time is not None
        assert source.last_successful_crawl_at is not None
        assert source.last_coze_status == "no_articles"
        assert source.last_coze_error is None


async def test_mismatched_batch_task_id_fails_before_document_persistence(
    app, test_settings
) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response("different-task", [_article("串单响应", "mismatch")])
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw),
        )

        result = await service.execute(task_id)

        assert result.status == "failed"
        assert result.provider_error_code == "COZE_TASK_ID_MISMATCH"
        assert await session.scalar(select(func.count(Document.id))) == 0
        invocation = await session.scalar(
            select(CozeInvocation).where(CozeInvocation.crawl_task_id == task_id)
        )
        assert invocation is not None
        assert invocation.status == "failed"
        assert invocation.error_code == "COZE_TASK_ID_MISMATCH"


async def test_failed_url_retry_rejects_mismatched_batch_task_id(app, test_settings) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        task = await session.get(CrawlTask, task_id)
        assert task is not None
        task.status = "partial_failed"
        task.current_stage = "partial_failed"
        task.provider_status = "partial_failed"
        task.failed_count = 1
        failure = CrawlTaskFailure(
            crawl_task_id=task_id,
            url="https://example.com/news/retry",
            stage="detail_fetch",
            error_code="HTTP_TIMEOUT",
            error_message="timed out",
            retryable=True,
            status="failed",
        )
        session.add(failure)
        await session.commit()
        await session.refresh(failure)
        raw = _batch_response("different-retry", [_article("重试串单", "retry")])
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw),
        )

        result = await service.execute_failed_url(failure.id)

        assert result.status == "failed"
        assert result.error_code == "COZE_TASK_ID_MISMATCH"
        assert await session.scalar(select(func.count(Document.id))) == 0
        invocation = await session.scalar(
            select(CozeInvocation).where(CozeInvocation.crawl_task_id == task_id)
        )
        assert invocation is not None
        assert invocation.status == "failed"
        assert invocation.error_code == "COZE_TASK_ID_MISMATCH"


async def test_failed_empty_batch_without_no_articles_warning_is_partial_failed(
    app, test_settings
) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response(task_id, [])
        raw["success"] = False
        raw["warnings"] = ["DYNAMIC_CONTENT_UNSUPPORTED"]
        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=FixtureProvider(raw),
        )

        result = await service.execute(task_id)

        assert result.status == "partial_failed"
        source = await session.scalar(select(Source))
        assert source is not None
        assert source.last_crawl_time is not None
        assert source.last_successful_crawl_at is None
        assert source.last_coze_status == "partial_failed"
        assert source.last_coze_error == "COZE_PARTIAL_FAILED"


async def test_active_sync_cancel_is_not_overwritten_when_remote_returns(
    app, test_settings
) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)
        raw = _batch_response(task_id, [_article("不会保存的中文标题", "cancelled")])

        class CancellingProvider(FixtureProvider):
            async def start_crawl(
                self,
                payload: Mapping[str, Any],
                *,
                contract: CrawlContract | None = None,
            ) -> CrawlProviderResult:
                async with app.state.database.session_factory() as cancel_session:
                    cancel_service = CrawlService(
                        CrawlRepository(cancel_session),
                        UnusedFetcher(),
                        _settings(test_settings),
                        crawl_provider=self,
                    )
                    cancelled = await cancel_service.cancel(task_id)
                    assert cancelled.provider_status == "cancel_requested_local_only"
                return await super().start_crawl(payload, contract=contract)

        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=CancellingProvider(raw),
        )
        result = await service.execute(task_id)

        assert result.status == "cancelled"
        assert result.provider_status == "remote_completed_local_processing_cancelled"

    async with app.state.database.session_factory() as verification_session:
        assert await verification_session.scalar(select(func.count(Document.id))) == 0
        invocation = await verification_session.scalar(
            select(CozeInvocation).where(CozeInvocation.crawl_task_id == task_id)
        )
        assert invocation is not None
        assert invocation.status == "completed_discarded_cancelled"
        assert invocation.raw_response_json == raw


async def test_active_sync_cancel_is_not_overwritten_when_remote_fails(app, test_settings) -> None:
    async with app.state.database.session_factory() as session:
        task_id = await _seed_task(session)

        class CancellingFailureProvider(FixtureProvider):
            async def start_crawl(
                self,
                payload: Mapping[str, Any],
                *,
                contract: CrawlContract | None = None,
            ) -> CrawlProviderResult:
                del payload, contract
                async with app.state.database.session_factory() as cancel_session:
                    cancel_service = CrawlService(
                        CrawlRepository(cancel_session),
                        UnusedFetcher(),
                        _settings(test_settings),
                        crawl_provider=self,
                    )
                    cancelled = await cancel_service.cancel(task_id)
                    assert cancelled.provider_status == "cancel_requested_local_only"
                raise CrawlProviderError(
                    "COZE_REMOTE_FAILURE",
                    "remote failure after cancellation",
                    retryable=True,
                )

        service = CrawlService(
            CrawlRepository(session),
            UnusedFetcher(),
            _settings(test_settings),
            crawl_provider=CancellingFailureProvider({}),
        )
        result = await service.execute(task_id)

        assert result.status == "cancelled"
        assert result.provider_status == "remote_failed_after_local_cancel"
        assert result.failed_count == 0

    async with app.state.database.session_factory() as verification_session:
        assert await verification_session.scalar(select(func.count(Document.id))) == 0
        invocation = await verification_session.scalar(
            select(CozeInvocation).where(CozeInvocation.crawl_task_id == task_id)
        )
        assert invocation is not None
        assert invocation.status == "failed"
        assert invocation.error_code == "COZE_REMOTE_FAILURE"
