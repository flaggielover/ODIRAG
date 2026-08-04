from __future__ import annotations

import shutil

from sqlalchemy import func, select

from app.crawler import FetchResponse
from app.models import Attachment, Document
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
