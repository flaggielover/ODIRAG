from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from app.config import Settings
from app.crawler import (
    CozeCrawlProvider,
    CrawlerAdapterRegistry,
    CrawlProvider,
    CrawlProviderError,
    Fetcher,
    normalize_url,
)
from app.crawler.state import CrawlTaskStateMachine, InvalidTaskTransitionError
from app.crawler.storage import FileStorage
from app.errors import AppError, NotFoundError
from app.models import (
    Attachment,
    CozeInvocation,
    CrawlTask,
    CrawlTaskFailure,
    DataLineage,
    Document,
    DocumentReview,
)
from app.repositories.crawl import CrawlRepository
from app.schemas.crawl import CrawlTaskCreate


class CrawlService:
    def __init__(
        self,
        repository: CrawlRepository,
        fetcher: Fetcher,
        settings: Settings,
        crawl_provider: CrawlProvider | None = None,
    ) -> None:
        self.repository = repository
        self.fetcher = fetcher
        self.settings = settings
        self.crawl_provider = crawl_provider or CozeCrawlProvider(
            api_token=(
                settings.coze_api_token.get_secret_value() if settings.coze_api_token else None
            ),
            legacy_api_url=settings.coze_legacy_api_url,
            batch_api_url=settings.coze_batch_api_url,
            default_contract=settings.coze_default_contract,
            timeout_seconds=settings.coze_timeout_seconds,
            max_retries=settings.coze_max_retries,
        )
        self.state = CrawlTaskStateMachine()
        self.storage = FileStorage(
            settings.data_dir / "attachments",
            max_bytes=settings.max_download_bytes,
            allowed_extensions=settings.allowed_attachment_extensions,
        )

    async def create(self, payload: CrawlTaskCreate) -> CrawlTask:
        column = await self.repository.get_column(payload.source_column_id)
        if column is None:
            raise NotFoundError("SourceColumn", payload.source_column_id)
        if not column.enabled or not column.source.enabled:
            raise AppError("SOURCE_DISABLED", "Source column is disabled", status_code=409)
        provider_name = payload.provider or column.source.crawl_provider
        if provider_name == "playwright":
            raise AppError(
                "CRAWL_PROVIDER_NOT_IMPLEMENTED",
                "The Playwright crawl provider is reserved but not implemented",
                status_code=422,
            )
        contract_mode = (
            payload.contract_mode
            or payload.provider_contract
            or column.source.coze_contract_mode
            or self.settings.coze_default_contract
        )
        return await self.repository.create_task(
            CrawlTask(
                source_column_id=payload.source_column_id,
                task_type=payload.task_type,
                trigger_type=payload.trigger_type,
                status="pending",
                provider_contract=contract_mode,
                max_articles=payload.max_articles,
                max_pages=payload.max_pages,
                crawl_provider=provider_name,
                provider=provider_name,
                contract_mode=contract_mode,
            )
        )

    async def list(self, *, status: str | None = None) -> list[CrawlTask]:
        return await self.repository.list_tasks(status=status)

    async def get(self, task_id: int) -> CrawlTask:
        task = await self.repository.get_task(task_id)
        if task is None:
            raise NotFoundError("CrawlTask", task_id)
        return task

    async def execute(self, task_id: int) -> CrawlTask:
        task = await self.repository.claim_task(task_id)
        if task is None:
            existing_task = await self.get(task_id)
            raise AppError(
                "TASK_ALREADY_CLAIMED",
                "Crawl task is not pending and cannot be claimed",
                status_code=409,
                details={"task_id": task_id, "status": existing_task.status},
            )
        column = task.source_column
        try:
            # Coze is the production default. Test fixtures from the pre-Coze schema can
            # continue to exercise the local crawler only in the test environment.
            if task.crawl_provider == "coze" and (
                self.settings.coze_enabled or self.settings.environment != "test"
            ):
                return await self._execute_coze(task, column)
            crawler = CrawlerAdapterRegistry.default(self.fetcher).get(column.parser_type)
            documents = await crawler.crawl_column(
                column_url=column.column_url,
                selectors=column.selectors_json,
                pagination=column.pagination_json,
                max_pages=column.max_pages,
                request_interval_seconds=column.request_interval_seconds,
            )
            task.discovered_count = len(documents)
            for crawled in documents:
                task.fetched_count += 1
                canonical_url = normalize_url(crawled.url)
                existing_document = await self.repository.find_document(
                    source_column_id=column.id, canonical_url=canonical_url
                )
                if existing_document is not None:
                    task.url_duplicate_count += 1
                    existing_document.last_crawl_time = datetime.now(UTC)
                    continue
                document = Document(
                    document_id=str(uuid.uuid4()),
                    source_id=column.source_id,
                    source_column_id=column.id,
                    title=crawled.title,
                    source_url=crawled.url,
                    canonical_url=canonical_url,
                    publish_date=_parse_date(crawled.publish_date_text),
                    region=column.source.region,
                    city=column.source.city,
                    content=crawled.text,
                    raw_content=crawled.raw_html,
                    content_hash=hashlib.sha256(crawled.text.encode("utf-8")).hexdigest(),
                    word_count=len(crawled.text),
                    language="zh" if re.search(r"[\u4e00-\u9fff]", crawled.text) else "unknown",
                    rule_filter_status="pending",
                    llm_review_status="pending",
                    manual_review_status="pending",
                    final_status="pending",
                    index_status="pending",
                    first_crawl_time=datetime.now(UTC),
                    last_crawl_time=datetime.now(UTC),
                )
                await self.repository.add_document(document)
                await self.repository.add_lineage(
                    DataLineage(
                        lineage_id=str(uuid.uuid4()),
                        source_id=column.source_id,
                        crawl_task_id=task.id,
                        document_id=document.id,
                    )
                )
                for discovered in crawled.attachments:
                    await self._download_attachment(document, discovered.name, discovered.url)
                task.success_count += 1
            column.source.last_crawl_time = datetime.now(UTC)
            column.source.last_successful_crawl_at = datetime.now(UTC)
            task.pending_review_count = task.success_count
            self.state.transition(task, "completed")
            await self.repository.commit()
            return await self.get(task.id)
        except Exception as exc:
            await self.repository.rollback()
            task = await self.get(task_id)
            if task.status == "running":
                task.failed_count += 1
                self.state.transition(task, "failed", error=exc.__class__.__name__)
                await self.repository.save_task(task)
            raise

    async def _execute_coze(self, task: CrawlTask, column: object) -> CrawlTask:
        """Run the configured Coze deployment and persist raw/normalized results."""

        from app.models.source import SourceColumn

        assert isinstance(column, SourceColumn)
        if not self.settings.coze_enabled:
            task.provider_error_code = "COZE_NOT_CONFIGURED"
            task.provider_error_message = "Coze crawling is disabled"
            task.provider_status = "failed"
            task.failed_count += 1
            self.state.transition(task, "failed", error=task.provider_error_code)
            await self.repository.save_task(task)
            return task
        contract = task.provider_contract or self.settings.coze_default_contract
        endpoint = (
            self.settings.coze_batch_api_url
            if contract == "batch_crawl"
            else self.settings.coze_legacy_api_url
        )
        if not endpoint:
            task.provider_error_code = (
                "COZE_BATCH_WORKFLOW_NOT_PUBLISHED"
                if contract == "batch_crawl"
                else "COZE_LEGACY_WORKFLOW_NOT_CONFIGURED"
            )
            task.provider_error_message = "The selected Coze workflow is not published"
            task.failed_count += 1
            self.state.transition(task, "failed", error=task.provider_error_code)
            await self.repository.save_task(task)
            return task
        now = datetime.now(UTC)
        task.provider_contract = contract
        task.contract_mode = contract
        task.current_stage = "calling_coze"
        task.provider_status = "calling_coze"
        self.state.transition(task, "calling_coze")
        payload = {
            "task_id": task.id,
            "source_url": column.column_url,
            "source_name": column.source.name,
            "region": column.source.region,
            "column_name": column.column_name,
            "max_articles": task.max_articles,
            "max_pages": task.max_pages,
            "minimum_content_length": 3000,
            "crawl_rules": {},
            "quality_rules": {},
            "include_html": True,
            "include_pdf": True,
            "include_docx": True,
            "include_xlsx": True,
            "deduplicate": True,
        }
        invocation = CozeInvocation(
            crawl_task_id=task.id,
            source_id=column.source_id,
            contract=contract,
            endpoint_url=_deployment_identifier(endpoint),
            deployment_identifier=_deployment_identifier(endpoint),
            status="calling",
            request_json=payload,
            token_usage_json={},
            started_at=now,
        )
        await self.repository.add_coze_invocation(invocation)
        await self.repository.commit()
        try:
            task.provider_status = "coze_running"
            self.state.transition(task, "coze_running")
            await self.repository.commit()
            result = await self.crawl_provider.start_crawl(payload, contract=contract)  # type: ignore[arg-type]
            invocation.status = "response_received"
            invocation.http_status_code = result.status_code
            invocation.attempt_count = result.attempts
            invocation.retry_count = max(0, result.attempts - 1)
            invocation.duration_ms = result.duration_ms
            invocation.raw_response_json = result.raw_response
            await self.repository.commit()
            await self.repository.session.refresh(task)
            if task.status == "cancelled":
                invocation.status = "completed_discarded_cancelled"
                invocation.finished_at = datetime.now(UTC)
                task.provider_status = "remote_completed_local_processing_cancelled"
                task.current_stage = "cancelled"
                await self.repository.commit()
                return await self.get(task.id)
            task.provider_status = "normalizing"
            self.state.transition(task, "normalizing")
            normalized, batch = self.crawl_provider.normalize_result(
                result.raw_response, contract=contract  # type: ignore[arg-type]
            )
            invocation.normalized_response_json = normalized
            invocation.status = "completed"
            invocation.finished_at = datetime.now(UTC)
            if batch is None:
                raise CrawlProviderError(
                    "COZE_BATCH_CONTRACT_REQUIRED",
                    "batch_crawl requires a strict batch response",
                    retryable=False,
                )
            task.discovered_count = batch.statistics.articles_discovered
            task.fetched_count = batch.statistics.articles_fetched
            task.failed_count = batch.statistics.articles_failed
            task.success_count = batch.statistics.articles_accepted
            task.accepted_count = batch.statistics.articles_accepted
            task.rejected_count = batch.statistics.articles_rejected
            task.pending_review_count = batch.statistics.articles_pending_review
            await self._persist_batch_failures(task, batch.failed_urls)
            task.provider_status = "saving_documents"
            self.state.transition(task, "saving_documents")
            for article in batch.articles:
                if article.decision == "failed":
                    await self._persist_failed_article(task, article)
                    continue
                try:
                    async with self.repository.session.begin_nested():
                        await self._save_coze_article(task, column, article)
                except Exception as exc:
                    await self.repository.add_failure(
                        CrawlTaskFailure(
                            crawl_task_id=task.id,
                            url=str(article.url),
                            stage="saving_documents",
                            error_code="LOCAL_DOCUMENT_SAVE_FAILED",
                            error_message=exc.__class__.__name__,
                            retryable=True,
                            status="pending",
                        )
                    )
                    task.failed_count += 1
                    if article.decision == "accepted":
                        task.accepted_count = max(0, task.accepted_count - 1)
                        task.success_count = task.accepted_count
                    elif article.decision == "rejected":
                        task.rejected_count = max(0, task.rejected_count - 1)
                    elif article.decision == "pending_review":
                        task.pending_review_count = max(0, task.pending_review_count - 1)
            column.source.last_crawl_time = datetime.now(UTC)
            no_articles = batch.statistics.articles_discovered == 0
            column.source.last_coze_status = (
                "partial_failed"
                if task.failed_count or not batch.success
                else "no_articles" if no_articles else "completed"
            )
            column.source.last_coze_article_count = len(batch.articles)
            column.source.last_coze_error = None
            column.source.last_successful_crawl_at = datetime.now(UTC)
            task.provider_error_code = None
            task.provider_error_message = None
            if task.failed_count or not batch.success:
                task.provider_status = "partial_failed"
                self.state.transition(task, "partial_failed", error="COZE_PARTIAL_FAILED")
            elif task.accepted_count or task.pending_review_count:
                task.provider_status = "waiting_review"
                self.state.transition(task, "waiting_review")
            else:
                task.provider_status = "no_articles" if no_articles else "completed"
                self.state.transition(task, "completed")
            await self.repository.commit()
            return await self.get(task.id)
        except CrawlProviderError as exc:
            invocation.status = "failed"
            invocation.error_code = exc.code
            invocation.error_message = str(exc)
            invocation.attempt_count = max(invocation.attempt_count, exc.attempts)
            invocation.retry_count = max(0, invocation.attempt_count - 1)
            if exc.status_code is not None:
                invocation.http_status_code = exc.status_code
            if invocation.raw_response_json is None:
                invocation.raw_response_json = exc.raw_response
            invocation.finished_at = datetime.now(UTC)
            task.provider_error_code = exc.code
            task.provider_error_message = str(exc)
            task.provider_status = "failed"
            task.failed_count += 1
            task.error_message = str(exc)
            if task.status not in {"failed", "cancelled", "completed", "partial_failed"}:
                self.state.transition(task, "failed", error=exc.code)
            column.source.last_coze_status = "failed"
            column.source.last_coze_error = exc.code
            await self.repository.commit()
            return await self.get(task.id)
        except Exception as exc:
            invocation.status = "failed"
            invocation.error_code = "COZE_INTERNAL_ERROR"
            invocation.error_message = exc.__class__.__name__
            invocation.finished_at = datetime.now(UTC)
            task.provider_error_code = "COZE_INTERNAL_ERROR"
            task.provider_error_message = exc.__class__.__name__
            task.provider_status = "failed"
            task.failed_count += 1
            task.error_message = exc.__class__.__name__
            if task.status not in {"failed", "cancelled", "completed", "partial_failed"}:
                self.state.transition(task, "failed", error="COZE_INTERNAL_ERROR")
            column.source.last_coze_status = "failed"
            column.source.last_coze_error = "COZE_INTERNAL_ERROR"
            await self.repository.commit()
            return await self.get(task.id)

    async def _persist_batch_failures(self, task: CrawlTask, failed_urls: Sequence[object]) -> None:
        for failed in failed_urls:
            url = str(getattr(failed, "url", ""))
            await self.repository.add_failure(
                CrawlTaskFailure(
                    crawl_task_id=task.id,
                    url=url,
                    stage=str(getattr(failed, "stage", "crawl")),
                    error_code=str(getattr(failed, "error_code", "COZE_ARTICLE_FAILED")),
                    error_message=str(getattr(failed, "error_message", "article failed")),
                    retryable=bool(getattr(failed, "retryable", False)),
                    status="pending",
                )
            )

    async def _persist_failed_article(self, task: CrawlTask, article: object) -> None:
        await self.repository.add_failure(
            CrawlTaskFailure(
                crawl_task_id=task.id,
                url=str(getattr(article, "url", "")),
                stage=str(getattr(article, "extraction_method", "article")),
                error_code="COZE_ARTICLE_FAILED",
                error_message=str(getattr(article, "decision_reason", "article failed")),
                retryable=True,
                status="pending",
            )
        )

    async def _save_coze_article(self, task: CrawlTask, column: object, article: object) -> None:
        from app.models.source import SourceColumn
        from app.schemas.coze import BatchArticle

        assert isinstance(column, SourceColumn)
        assert isinstance(article, BatchArticle)
        canonical_url = normalize_url(str(article.url))
        existing = await self.repository.find_document(
            source_column_id=column.id, canonical_url=canonical_url
        )
        if existing is not None:
            task.url_duplicate_count += 1
            existing.last_crawl_time = datetime.now(UTC)
            await self.repository.ensure_document_lineage(
                task_id=task.id,
                source_id=column.source_id,
                document_id=existing.id,
            )
            return
        decision = article.decision
        final_status = {
            "accepted": "pending_manual_review",
            "pending_review": "pending_manual_review",
            "rejected": "rejected",
            "failed": "failed",
        }[decision]
        normalized_quality = (
            (article.quality_score / 100) if article.quality_score is not None else None
        )
        document = Document(
            document_id=str(uuid.uuid4()),
            source_id=column.source_id,
            source_column_id=column.id,
            title=article.title,
            source_url=str(article.url),
            canonical_url=canonical_url,
            publish_date=(
                article.published_at.date()
                if isinstance(article.published_at, datetime)
                else article.published_at
            ),
            region=article.region or column.source.region,
            content=article.content,
            raw_content=article.content,
            content_hash=hashlib.sha256(article.content.encode("utf-8")).hexdigest(),
            word_count=len(article.content),
            language="zh" if re.search(r"[\u4e00-\u9fff]", article.content) else "unknown",
            document_type=article.document_type,
            quality_score=normalized_quality,
            rule_filter_status=decision,
            llm_review_status=decision,
            manual_review_status=(
                "pending" if decision in {"accepted", "pending_review"} else decision
            ),
            final_status=final_status,
            index_status="pending",
            first_crawl_time=datetime.now(UTC),
            last_crawl_time=datetime.now(UTC),
        )
        await self.repository.add_document(document)
        await self.repository.session.flush()
        self.repository.session.add(
            DocumentReview(
                document_id=document.id,
                review_type="coze_quality",
                reviewer="coze_workflow",
                decision=decision,
                quality_score=normalized_quality,
                document_type=article.document_type,
                topics_json=article.keywords,
                summary=article.summary,
                reasons_json=[article.decision_reason, *article.warnings],
                extracted_fields_json={
                    "organization": article.organization,
                    "region": article.region,
                    "column_name": article.column_name,
                    "extraction_method": article.extraction_method,
                    "needs_ocr": article.needs_ocr,
                    "image_urls": [str(url) for url in article.image_urls],
                    "image_count": article.image_count,
                    "image_alt_texts": article.image_alt_texts,
                },
                model_name="coze-workflow",
                raw_response=article.model_dump_json(),
            )
        )
        await self.repository.add_lineage(
            DataLineage(
                lineage_id=str(uuid.uuid4()),
                source_id=column.source_id,
                crawl_task_id=task.id,
                document_id=document.id,
            )
        )
        for attachment in article.attachments:
            await self.repository.add_attachment(
                Attachment(
                    document_id=document.id,
                    attachment_name=attachment.name,
                    source_url=str(attachment.url),
                    download_status=(
                        "completed"
                        if attachment.download_status == "success"
                        else attachment.download_status
                    ),
                    parse_status="pending",
                    parsed_text=attachment.extracted_text,
                    requires_ocr=article.needs_ocr,
                    error_message=attachment.error_message,
                )
            )

    async def retry(self, task_id: int) -> CrawlTask:
        task = await self.get(task_id)
        try:
            self.state.transition(task, "pending")
        except InvalidTaskTransitionError as exc:
            raise AppError("INVALID_TASK_STATE", str(exc), status_code=409) from exc
        task.retry_count += 1
        return await self.repository.save_task(task)

    async def queue_failure_retry(self, task_id: int, failure_id: int) -> CrawlTaskFailure:
        await self.get(task_id)
        failure = await self.repository.get_failure(failure_id)
        if failure is None or failure.crawl_task_id != task_id:
            raise NotFoundError("CrawlTaskFailure", failure_id)
        if not failure.retryable:
            raise AppError(
                "CRAWL_FAILURE_NOT_RETRYABLE",
                "The failed URL is not marked retryable",
                status_code=409,
            )
        if failure.status in {"queued", "retrying", "succeeded"}:
            raise AppError(
                "CRAWL_FAILURE_ALREADY_HANDLED",
                f"Failed URL is already {failure.status}",
                status_code=409,
            )
        failure.status = "queued"
        failure.next_retry_at = None
        await self.repository.commit()
        await self.repository.session.refresh(failure)
        return failure

    async def mark_failure_queue_error(self, failure_id: int, error_type: str) -> None:
        failure = await self.repository.get_failure(failure_id)
        if failure is None:
            return
        failure.status = "failed"
        failure.error_message = f"TASK_QUEUE_UNAVAILABLE:{error_type}"
        failure.next_retry_at = datetime.now(UTC) + timedelta(minutes=1)
        await self.repository.commit()

    async def execute_failed_url(self, failure_id: int) -> CrawlTaskFailure:
        failure = await self.repository.get_failure(failure_id)
        if failure is None:
            raise NotFoundError("CrawlTaskFailure", failure_id)
        if failure.status not in {"queued", "pending", "failed"} or not failure.retryable:
            raise AppError(
                "CRAWL_FAILURE_ALREADY_HANDLED",
                f"Failed URL cannot run from status {failure.status}",
                status_code=409,
            )
        task = failure.crawl_task
        column = task.source_column
        failure.status = "retrying"
        failure.retry_count += 1
        failure.last_attempt_at = datetime.now(UTC)
        task.current_stage = "retrying_failed_url"
        await self.repository.commit()
        contract = "batch_crawl"
        endpoint = self.settings.coze_batch_api_url
        if not self.settings.coze_enabled or not endpoint:
            return await self._fail_failure_retry(
                failure, task, "COZE_BATCH_WORKFLOW_NOT_PUBLISHED"
            )
        payload: dict[str, object] = {
            "task_id": f"{task.id}:failure:{failure.id}",
            "source_url": failure.url,
            "source_name": column.source.name,
            "region": column.source.region,
            "column_name": column.column_name,
            "max_articles": 1,
            "max_pages": 1,
            "minimum_content_length": 3000,
            "include_html": True,
            "include_pdf": True,
            "include_docx": True,
            "include_xlsx": True,
            "deduplicate": True,
            "crawl_rules": {},
            "quality_rules": {},
        }
        invocation = CozeInvocation(
            crawl_task_id=task.id,
            source_id=column.source_id,
            contract=contract,
            endpoint_url=_deployment_identifier(endpoint),
            deployment_identifier=_deployment_identifier(endpoint),
            status="retrying_failed_url",
            request_json=payload,
            token_usage_json={},
            started_at=datetime.now(UTC),
        )
        await self.repository.add_coze_invocation(invocation)
        await self.repository.commit()
        try:
            result = await self.crawl_provider.start_crawl(payload, contract="batch_crawl")
            invocation.http_status_code = result.status_code
            invocation.attempt_count = result.attempts
            invocation.retry_count = max(0, result.attempts - 1)
            invocation.duration_ms = result.duration_ms
            invocation.raw_response_json = result.raw_response
            invocation.status = "response_received"
            await self.repository.commit()
            normalized, batch = self.crawl_provider.normalize_result(
                result.raw_response, contract="batch_crawl"
            )
            invocation.normalized_response_json = normalized
            invocation.finished_at = datetime.now(UTC)
            if (
                batch is None
                or batch.failed_urls
                or not batch.articles
                or any(article.decision == "failed" for article in batch.articles)
            ):
                invocation.status = "failed"
                return await self._fail_failure_retry(failure, task, "COZE_RETRY_UNRESOLVED")
            invocation.status = "completed"
            for article in batch.articles:
                async with self.repository.session.begin_nested():
                    await self._save_coze_article(task, column, article)
            failure.status = "succeeded"
            failure.resolved_at = datetime.now(UTC)
            failure.next_retry_at = None
            task.failed_count = max(0, task.failed_count - 1)
            task.accepted_count += batch.statistics.articles_accepted
            task.rejected_count += batch.statistics.articles_rejected
            task.pending_review_count += batch.statistics.articles_pending_review
            task.current_stage = "failed_url_retry_completed"
            if await self.repository.count_unresolved_failures(task.id) == 0:
                task.next_retry_at = None
                if task.status == "partial_failed":
                    if task.accepted_count or task.pending_review_count:
                        task.provider_status = "waiting_review"
                        self.state.transition(task, "waiting_review")
                    else:
                        task.provider_status = "completed"
                        self.state.transition(task, "completed")
            await self.repository.commit()
            return failure
        except CrawlProviderError as exc:
            invocation.status = "failed"
            invocation.error_code = exc.code
            invocation.error_message = str(exc)
            invocation.attempt_count = max(invocation.attempt_count, exc.attempts)
            invocation.retry_count = max(0, invocation.attempt_count - 1)
            if exc.status_code is not None:
                invocation.http_status_code = exc.status_code
            if invocation.raw_response_json is None:
                invocation.raw_response_json = exc.raw_response
            invocation.finished_at = datetime.now(UTC)
            return await self._fail_failure_retry(failure, task, exc.code)
        except Exception as exc:
            invocation.status = "failed"
            invocation.error_code = "LOCAL_FAILED_URL_RETRY_ERROR"
            invocation.error_message = exc.__class__.__name__
            invocation.finished_at = datetime.now(UTC)
            return await self._fail_failure_retry(failure, task, "LOCAL_FAILED_URL_RETRY_ERROR")

    async def _fail_failure_retry(
        self, failure: CrawlTaskFailure, task: CrawlTask, error_code: str
    ) -> CrawlTaskFailure:
        failure.status = "failed"
        failure.error_code = error_code
        delay_seconds = min(3600, 60 * (2 ** min(failure.retry_count, 6)))
        failure.next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        task.next_retry_at = failure.next_retry_at
        task.current_stage = "failed_url_retry_failed"
        await self.repository.commit()
        return failure

    async def mark_queue_failure(self, task_id: int, *, error_type: str) -> CrawlTask:
        """Make a persisted-but-unqueued task recoverable through the retry API."""
        task = await self.get(task_id)
        if task.status not in {"pending", "queued"}:
            return task
        self.state.transition(task, "failed", error=f"TASK_QUEUE_UNAVAILABLE:{error_type}")
        task.failed_count += 1
        return await self.repository.save_task(task)

    async def mark_queued(self, task_id: int) -> CrawlTask:
        task = await self.get(task_id)
        if task.status == "pending":
            self.state.transition(task, "queued")
            return await self.repository.save_task(task)
        return task

    async def cancel(self, task_id: int) -> CrawlTask:
        task = await self.get(task_id)
        active_remote = task.status in {"calling_coze", "coze_running"}
        try:
            self.state.transition(task, "cancelled")
        except InvalidTaskTransitionError as exc:
            raise AppError("INVALID_TASK_STATE", str(exc), status_code=409) from exc
        if active_remote:
            task.provider_status = "cancel_requested_local_only"
            task.provider_error_message = (
                "The synchronous Coze request cannot be cancelled remotely; "
                "local normalization and document saving will be skipped."
            )
        else:
            task.provider_status = "cancelled_before_start"
        return await self.repository.save_task(task)

    async def _download_attachment(self, document: Document, name: str, url: str) -> None:
        attachment = Attachment(
            document_id=document.id,
            attachment_name=name,
            source_url=url,
            file_extension=(
                ("." + url.rsplit(".", 1)[-1].lower()) if "." in url.rsplit("/", 1)[-1] else None
            ),
            download_status="pending",
            parse_status="pending",
        )
        await self.repository.add_attachment(attachment)
        try:
            response = await self.fetcher.fetch(url)
            path = self.storage.save(
                source_url=url,
                content=response.content,
                namespace=document.document_id,
            )
            attachment.local_path = str(path)
            attachment.mime_type = response.content_type
            attachment.file_size = len(response.content)
            attachment.file_hash = hashlib.sha256(response.content).hexdigest()
            attachment.download_status = "completed"
        except Exception as exc:
            attachment.download_status = "failed"
            attachment.error_message = exc.__class__.__name__


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    value = value.replace("\u5e74", "-").replace("\u6708", "-").replace("\u65e5", "")
    match = re.search(r"(20\d{2})[-年/.](\d{1,2})[-月/.](\d{1,2})", value)
    if not match:
        return None
    try:
        return date(*(int(part) for part in match.groups()))
    except ValueError:
        return None


def _deployment_identifier(endpoint: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(endpoint)
    host = parsed.hostname or "unknown"
    suffix = hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:12]
    return f"{parsed.scheme or 'https'}://{host}#{suffix}"
