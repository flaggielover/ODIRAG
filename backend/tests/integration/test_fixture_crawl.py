from __future__ import annotations

import shutil
from collections.abc import Mapping
from typing import Any

import pytest
from sqlalchemy import func, select

from app.crawler import FetchResponse
from app.crawler.providers import CrawlContract, CrawlProviderResult
from app.errors import AppError
from app.models import Attachment, Document, DocumentReview
from app.repositories.crawl import CrawlRepository
from app.repositories.sources import SourceRepository
from app.schemas.crawl import CrawlTaskCreate
from app.schemas.source import SourceColumnCreate, SourceCreate
from app.services.crawl import CrawlService
from app.services.sources import SourceService


class FixtureFetcher:
    def __init__(self) -> None:
        self.responses = {
            "https://fixture.gov/list.html": _html(
                "https://fixture.gov/list.html",
                '<html><body><a class="item" href="/policy/1.html">一</a>'
                '<a class="item" href="/policy/2.html?utm_source=x">二</a></body></html>',
            ),
            "https://fixture.gov/policy/1.html": _html(
                "https://fixture.gov/policy/1.html",
                "<html><h1>软件产业支持办法</h1><time>2026-01-02</time>"
                "<article><p>支持软件企业研发。</p>"
                '<a class="attachment" href="/files/rules.txt">附件</a></article></html>',
            ),
            "https://fixture.gov/policy/2.html": _html(
                "https://fixture.gov/policy/2.html",
                "<html><h1>数字经济申报通知</h1><time>2026年02月03日</time>"
                "<article><p>符合条件的企业可以申报。</p></article></html>",
            ),
            "https://fixture.gov/files/rules.txt": FetchResponse(
                "https://fixture.gov/files/rules.txt",
                200,
                "附件正文".encode(),
                "text/plain",
                "utf-8",
            ),
        }

    async def fetch(self, url: str) -> FetchResponse:
        return self.responses[url]


def _html(url: str, content: str) -> FetchResponse:
    return FetchResponse(url, 200, content.encode(), "text/html", "utf-8")


async def test_fixture_crawl_is_idempotent_and_downloads_attachments(app) -> None:
    settings = app.state.settings
    try:
        async with app.state.database.session_factory() as session:
            source = await SourceService(SourceRepository(session)).create(
                SourceCreate(
                    source_key="fixture-crawl",
                    name="Fixture crawl",
                    domain="fixture.gov",
                    homepage_url="https://fixture.gov/",
                    region="四川",
                    columns=[
                        SourceColumnCreate(
                            column_key="policies",
                            column_name="政策",
                            column_url="https://fixture.gov/list.html",
                            max_pages=1,
                            request_interval_seconds=0,
                            selectors_json={
                                "list_link": "a.item",
                                "title": "h1",
                                "content": "article",
                                "publish_date": "time",
                                "attachment": "a.attachment",
                            },
                        )
                    ],
                )
            )
            column_id = source.columns[0].id
            service = CrawlService(CrawlRepository(session), FixtureFetcher(), settings)
            first = await service.create(
                CrawlTaskCreate(source_column_id=column_id, execution_mode="inline")
            )
            first = await service.execute(first.id)
            assert first.status == "completed"
            assert first.success_count == 2
            second = await service.create(
                CrawlTaskCreate(source_column_id=column_id, execution_mode="inline")
            )
            second = await service.execute(second.id)
            assert second.status == "completed"
            assert second.url_duplicate_count == 2
            document_count = await session.scalar(select(func.count()).select_from(Document))
            attachment = await session.scalar(select(Attachment))
            assert document_count == 2
            assert attachment is not None
            assert attachment.download_status == "completed"
            assert attachment.local_path is not None
    finally:
        shutil.rmtree(settings.data_dir, ignore_errors=True)


async def test_explicit_local_provider_runs_through_worker_contract(app) -> None:
    settings = app.state.settings
    try:
        async with app.state.database.session_factory() as session:
            source = await SourceService(SourceRepository(session)).create(
                SourceCreate(
                    source_key="fixture-local-provider",
                    name="Fixture Local Provider",
                    domain="fixture.gov",
                    homepage_url="https://fixture.gov/",
                    region="四川",
                    crawl_provider="local",
                    columns=[
                        SourceColumnCreate(
                            column_key="policies",
                            column_name="政策",
                            column_url="https://fixture.gov/list.html",
                            max_pages=1,
                            request_interval_seconds=0,
                            selectors_json={
                                "list_link": "a.item",
                                "title": "h1",
                                "content": "article",
                                "publish_date": "time",
                            },
                        )
                    ],
                )
            )
            service = CrawlService(
                CrawlRepository(session),
                FixtureFetcher(),
                settings,
            )
            task = await service.create(
                CrawlTaskCreate(source_column_id=source.columns[0].id, provider="local")
            )
            result = await service.execute(task.id)

            assert result.status == "waiting_review"
            assert result.provider == "local"
            assert result.contract_mode == "batch_crawl"
            assert result.provider_contract == "batch_crawl"
            assert result.provider_status == "waiting_review"
            assert result.finished_at is None
            assert result.pending_review_count == 2
            assert result.failed_count == 0
            assert await session.scalar(select(func.count(Document.id))) == 2
            document = await session.scalar(select(Document).order_by(Document.id))
            review = await session.scalar(select(DocumentReview).order_by(DocumentReview.id))
            assert document is not None
            assert document.rule_filter_status == "pending"
            assert document.llm_review_status == "pending"
            assert review is not None
            assert review.review_type == "local_extraction"
            assert review.reviewer == "local_crawler"
            assert review.model_name is None
    finally:
        shutil.rmtree(settings.data_dir, ignore_errors=True)


async def test_explicit_local_provider_does_not_overwrite_concurrent_cancel(
    app, monkeypatch
) -> None:
    settings = app.state.settings
    try:
        async with app.state.database.session_factory() as session:
            source = await SourceService(SourceRepository(session)).create(
                SourceCreate(
                    source_key="fixture-local-provider-cancel",
                    name="Fixture Local Provider Cancel",
                    domain="fixture.gov",
                    homepage_url="https://fixture.gov/",
                    crawl_provider="local",
                    columns=[
                        SourceColumnCreate(
                            column_key="policies",
                            column_name="政策",
                            column_url="https://fixture.gov/list.html",
                            max_pages=1,
                            request_interval_seconds=0,
                            selectors_json={
                                "list_link": "a.item",
                                "title": "h1",
                                "content": "article",
                                "publish_date": "time",
                            },
                        )
                    ],
                )
            )
            service = CrawlService(CrawlRepository(session), FixtureFetcher(), settings)
            task = await service.create(
                CrawlTaskCreate(source_column_id=source.columns[0].id, provider="local")
            )
            original_start = service.local_provider.start_crawl

            async def cancel_before_return(
                payload: Mapping[str, Any],
                *,
                contract: CrawlContract | None = None,
            ) -> CrawlProviderResult:
                async with app.state.database.session_factory() as cancel_session:
                    cancel_service = CrawlService(
                        CrawlRepository(cancel_session), FixtureFetcher(), settings
                    )
                    cancelled = await cancel_service.cancel(task.id)
                    assert cancelled.provider_status == "cancel_requested_local_only"
                return await original_start(payload, contract=contract)

            monkeypatch.setattr(service.local_provider, "start_crawl", cancel_before_return)
            result = await service.execute(task.id)

            assert result.status == "cancelled"
            assert result.provider_status == "local_completed_discarded_cancelled"

        async with app.state.database.session_factory() as verification_session:
            assert await verification_session.scalar(select(func.count(Document.id))) == 0
            assert await verification_session.scalar(select(func.count(DocumentReview.id))) == 0
    finally:
        shutil.rmtree(settings.data_dir, ignore_errors=True)


async def test_legacy_coze_contract_is_rejected_for_column_tasks(app) -> None:
    settings = app.state.settings
    try:
        async with app.state.database.session_factory() as session:
            source = await SourceService(SourceRepository(session)).create(
                SourceCreate(
                    source_key="fixture-legacy-contract",
                    name="Fixture Legacy Contract",
                    domain="fixture.gov",
                    homepage_url="https://fixture.gov/",
                    coze_contract_mode="legacy_single_article",
                    columns=[
                        SourceColumnCreate(
                            column_key="policies",
                            column_name="政策",
                            column_url="https://fixture.gov/list.html",
                        )
                    ],
                )
            )
            service = CrawlService(CrawlRepository(session), FixtureFetcher(), settings)

            with pytest.raises(AppError) as exc_info:
                await service.create(CrawlTaskCreate(source_column_id=source.columns[0].id))

            assert exc_info.value.code == "COZE_LEGACY_SINGLE_ARTICLE_ONLY"
            assert exc_info.value.status_code == 422

            local_task = await service.create(
                CrawlTaskCreate(source_column_id=source.columns[0].id, provider="local")
            )
            assert local_task.contract_mode == "batch_crawl"
            assert local_task.provider_contract == "batch_crawl"

            with pytest.raises(AppError) as local_exc_info:
                await service.create(
                    CrawlTaskCreate(
                        source_column_id=source.columns[0].id,
                        provider="local",
                        contract_mode="legacy_single_article",
                    )
                )

            assert local_exc_info.value.code == "LOCAL_CONTRACT_UNSUPPORTED"
            assert local_exc_info.value.status_code == 422
    finally:
        shutil.rmtree(settings.data_dir, ignore_errors=True)
