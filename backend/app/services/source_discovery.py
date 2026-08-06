from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

from bs4 import BeautifulSoup, Tag
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.crawler import FetchResponse, HttpFetcher, normalize_url
from app.errors import AppError, ConflictError, NotFoundError
from app.models import (
    Source,
    SourceCandidate,
    SourceCandidateColumn,
    SourceColumn,
    SourceDiscoveryEvent,
    SourceDiscoveryRun,
)
from app.repositories.source_discovery import SourceDiscoveryRepository
from app.schemas.source_discovery import SourceDiscoveryRunCreate
from app.source_discovery import CandidateDiscoveryProvider, build_candidate_provider

_COLUMN_TERMS = (
    "政策",
    "通知",
    "公告",
    "公示",
    "政务公开",
    "法规",
    "文件",
    "办事",
    "新闻",
    "动态",
    "policy",
    "notice",
    "announcement",
    "document",
    "government",
    "open",
)
_DETAIL_EXTENSIONS = {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".zip"}
_MARKERS = ("政府", "政务", "人民政府", "government", "official", "gov")


@dataclass(frozen=True, slots=True)
class TrialStats:
    discovered: int
    fetched: int
    success: int
    failed: int
    average_chars: int


class SourceDiscoveryService:
    """Execute and audit the content-gap to activated-source workflow."""

    def __init__(
        self,
        repository: SourceDiscoveryRepository,
        settings: Settings,
        *,
        provider: CandidateDiscoveryProvider | None = None,
        fetcher: HttpFetcher | None = None,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.provider = provider or build_candidate_provider(settings)
        self.fetcher = fetcher or HttpFetcher(
            timeout_seconds=settings.crawler_timeout_seconds,
            max_bytes=min(settings.max_download_bytes, 4 * 1024 * 1024),
            max_redirects=settings.crawler_max_redirects,
            user_agent="ODIRAG/0.1 source-discovery",
        )

    async def create(
        self, payload: SourceDiscoveryRunCreate, *, created_by: str
    ) -> SourceDiscoveryRun:
        source_count, document_count, evidence = await self.repository.content_gap(
            topic=payload.topic,
            region=payload.region,
            required_source_count=payload.required_source_count,
            required_document_count=payload.required_document_count,
        )
        query_text = payload.query_text or _build_query(
            payload.topic, payload.region, payload.organization_level
        )
        run = SourceDiscoveryRun(
            topic=payload.topic.strip(),
            region=payload.region,
            organization_level=payload.organization_level,
            query_text=query_text,
            required_source_count=payload.required_source_count,
            required_document_count=payload.required_document_count,
            existing_source_count=source_count,
            existing_document_count=document_count,
            gap_detected=bool(evidence["gap_detected"]),
            gap_evidence_json=evidence,
            status="pending" if evidence["gap_detected"] else "no_gap",
            discovery_provider=self.provider.name,
            max_candidates=payload.max_candidates or self.settings.source_discovery_max_candidates,
            created_by=created_by,
        )
        now = datetime.now(UTC)
        if not run.gap_detected:
            run.finished_at = now
        await self.repository.create_run(run)
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=run.id,
                stage="content_gap_detection",
                from_status=None,
                to_status=run.status,
                message=(
                    "Content gap detected; discovery queued."
                    if run.gap_detected
                    else "No content gap detected; discovery was not started."
                ),
                details_json=evidence,
            )
        )
        await self.repository.commit()
        return run

    async def execute(self, run_id: int) -> SourceDiscoveryRun:
        run = await self.repository.claim_run(run_id)
        if run is None:
            current = await self.get_run(run_id)
            if current.status in {"no_gap", "awaiting_approval", "activated"}:
                return current
            raise AppError(
                "SOURCE_DISCOVERY_ALREADY_CLAIMED",
                "Source discovery run is already running or not retryable",
                status_code=409,
                details={"run_id": run_id, "status": current.status},
            )
        try:
            hits = await self.provider.search(run.query_text, limit=run.max_candidates)
            seen_urls: set[str] = set()
            processed = 0
            for hit in hits:
                if processed >= run.max_candidates:
                    break
                try:
                    homepage = normalize_url(hit.url)
                except ValueError:
                    continue
                if homepage in seen_urls:
                    continue
                seen_urls.add(homepage)
                candidate = await self.repository.get_candidate_by_url(
                    run_id=run.id, homepage_url=homepage
                )
                if candidate is None:
                    candidate = SourceCandidate(
                        run_id=run.id,
                        canonical_homepage_url=homepage,
                        domain=(urlsplit(homepage).hostname or "").lower().rstrip("."),
                        name=hit.title[:512] or (urlsplit(homepage).hostname or homepage),
                        snippet=hit.snippet,
                        search_rank=hit.rank,
                        discovery_provider=self.provider.name,
                        discovery_query=run.query_text,
                    )
                    try:
                        await self.repository.create_candidate(candidate)
                    except IntegrityError:
                        await self.repository.rollback()
                        continue
                    previous_status = None
                elif run.attempt_count > 1 and candidate.status in {
                    "validation_failed",
                    "rejected",
                    "failed",
                }:
                    previous_status = candidate.status
                    await self.repository.reset_candidate_for_retry(candidate)
                else:
                    continue
                try:
                    await self.repository.add_event(
                        SourceDiscoveryEvent(
                            run_id=run.id,
                            candidate_id=candidate.id,
                            stage="candidate_discovery",
                            from_status=previous_status,
                            to_status="discovered",
                            message=(
                                "Candidate was rediscovered for a retry attempt."
                                if previous_status
                                else "Candidate returned by the configured search provider."
                            ),
                            details_json={
                                "rank": hit.rank,
                                "url": homepage,
                                "attempt_count": run.attempt_count,
                            },
                        )
                    )
                    await self.repository.commit()
                except Exception:
                    await self.repository.rollback()
                    raise
                processed += 1
                await self._process_candidate(run, candidate)

            run = await self.repository.refresh_run_counts(run.id)
            pending = await self.repository.list_candidates(run.id)
            if any(candidate.status == "pending_approval" for candidate in pending):
                run.status = "awaiting_approval"
            elif processed:
                run.status = "failed"
                run.error_message = "No candidate passed official validation and quality scoring."
            else:
                run.status = "failed"
                run.error_message = "Candidate discovery returned no usable URLs."
            run.finished_at = datetime.now(UTC)
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    stage="run_completion",
                    from_status="running",
                    to_status=run.status,
                    message="Source discovery run completed its automated stages.",
                    details_json={
                        "processed_candidates": processed,
                        "pending_approval": sum(
                            candidate.status == "pending_approval" for candidate in pending
                        ),
                    },
                )
            )
            await self.repository.save_run(run)
            return run
        except Exception as exc:
            await self.repository.rollback()
            failed = await self.repository.get_run(run_id)
            if failed is not None:
                failed.status = "failed"
                failed.finished_at = datetime.now(UTC)
                failed.error_message = exc.__class__.__name__
                await self.repository.add_event(
                    SourceDiscoveryEvent(
                        run_id=run_id,
                        stage="run_failure",
                        from_status="running",
                        to_status="failed",
                        message=(
                            "Source discovery run failed; provider or network details "
                            "were redacted."
                        ),
                        details_json={"error_type": exc.__class__.__name__},
                    )
                )
                await self.repository.save_run(failed)
            raise

    async def _process_candidate(self, run: SourceDiscoveryRun, candidate: SourceCandidate) -> None:
        try:
            response = await self._validate_official_status(run, candidate)
            if response is None:
                return
            columns = await self._discover_columns(run, candidate, response)
            if not columns:
                candidate.status = "failed"
                candidate.rejection_reason = "NO_POLICY_COLUMNS_DISCOVERED"
                await self.repository.add_event(
                    SourceDiscoveryEvent(
                        run_id=run.id,
                        candidate_id=candidate.id,
                        stage="column_discovery",
                        from_status="validated",
                        to_status="failed",
                        message="No same-site policy or public-information column was found.",
                        details_json={},
                    )
                )
                await self.repository.commit()
                return
            for column in columns:
                await self._trial_crawl_column(run, candidate, column)
            await self._score_candidate(run, candidate, columns)
        except Exception as exc:
            await self.repository.rollback()
            current = await self.repository.get_candidate(candidate.id)
            if current is None:
                return
            previous_status = current.status
            current.status = "failed"
            current.rejection_reason = exc.__class__.__name__
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=current.id,
                    stage="candidate_failure",
                    from_status=previous_status,
                    to_status="failed",
                    message=(
                        "Candidate processing failed; exception details are recorded "
                        "by type only."
                    ),
                    details_json={"error_type": exc.__class__.__name__},
                )
            )
            await self.repository.commit()

    async def _validate_official_status(
        self, run: SourceDiscoveryRun, candidate: SourceCandidate
    ) -> FetchResponse | None:
        try:
            response = await self.fetcher.fetch(candidate.canonical_homepage_url)
        except Exception as exc:
            candidate.status = "validation_failed"
            candidate.official_status = "validation_failed"
            candidate.rejection_reason = exc.__class__.__name__
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="official_status_validation",
                    from_status="discovered",
                    to_status="validation_failed",
                    message="Candidate homepage could not be fetched safely.",
                    details_json={"error_type": exc.__class__.__name__},
                )
            )
            await self.repository.commit()
            return None
        initial = urlsplit(candidate.canonical_homepage_url)
        final = urlsplit(response.url)
        host = (initial.hostname or "").lower().rstrip(".")
        final_host = (final.hostname or "").lower().rstrip(".")
        same_site = bool(host and final_host and _same_site(host, final_host))
        suffix = _trusted_suffix(final_host, self.settings.source_discovery_official_suffixes)
        body = response.text[:100_000].lower()
        markers = [marker for marker in _MARKERS if marker.lower() in body]
        score = (0.60 if suffix else 0.0) + (0.25 if final.scheme == "https" else 0.0)
        score += 0.15 if markers else 0.0
        evidence = {
            "initial_host": host,
            "final_host": final_host,
            "status_code": response.status_code,
            "same_site": same_site,
            "trusted_suffix": suffix,
            "https": final.scheme == "https",
            "marker_matches": markers,
        }
        candidate.validation_status_code = response.status_code
        candidate.validation_final_url = response.url
        candidate.official_score = Decimal(str(round(score, 4)))
        candidate.official_evidence_json = evidence
        if not same_site or not suffix or final.scheme != "https":
            candidate.official_status = "unverified"
            candidate.status = "validation_failed"
            candidate.rejection_reason = "OFFICIAL_STATUS_NOT_VERIFIED"
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="official_status_validation",
                    from_status="discovered",
                    to_status="validation_failed",
                    message=(
                        "Homepage was reachable but did not satisfy the configured "
                        "official-site policy."
                    ),
                    details_json=evidence,
                )
            )
            await self.repository.commit()
            return None
        candidate.official_status = "official"
        candidate.status = "validated"
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=run.id,
                candidate_id=candidate.id,
                stage="official_status_validation",
                from_status="discovered",
                to_status="validated",
                message="Homepage passed public-host and official-domain validation.",
                details_json=evidence,
            )
        )
        await self.repository.commit()
        return response

    async def _discover_columns(
        self, run: SourceDiscoveryRun, candidate: SourceCandidate, response: FetchResponse
    ) -> list[SourceCandidateColumn]:
        soup = BeautifulSoup(response.text, "lxml")
        base_host = (urlsplit(response.url).hostname or "").lower().rstrip(".")
        scored: list[tuple[int, str, str, list[str]]] = []
        seen: set[str] = set()
        for element in soup.select("a[href]"):
            if not isinstance(element, Tag):
                continue
            raw_href = element.get("href")
            if not isinstance(raw_href, str):
                continue
            try:
                url = normalize_url(raw_href, base_url=response.url)
            except ValueError:
                continue
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower().rstrip(".")
            if not host or not _same_site(base_host, host) or url in seen:
                continue
            if parsed.path.lower().endswith(tuple(_DETAIL_EXTENSIONS)):
                continue
            label = element.get_text(" ", strip=True)
            haystack = f"{label} {parsed.path}".lower()
            matches = [term for term in _COLUMN_TERMS if term.lower() in haystack]
            if not matches:
                continue
            seen.add(url)
            scored.append((len(matches), url, label or parsed.path.rsplit("/", 1)[-1], matches))
        scored.sort(key=lambda item: (-item[0], item[1]))
        columns: list[SourceCandidateColumn] = []
        for rank, (_score, url, label, matches) in enumerate(
            scored[: self.settings.source_discovery_max_columns], start=1
        ):
            key = _column_key(label, url, rank)
            column = SourceCandidateColumn(
                candidate_id=candidate.id,
                column_key=key,
                column_name=label[:255] or key,
                column_url=url,
                parser_type="html",
                selectors_json={
                    "list_link": "a[href]",
                    "title": "h1, title",
                    "content": (
                        "article, main, [role='main'], .article, .detail, "
                        ".content, #content, .article-content, .detail-content"
                    ),
                },
                pagination_json={"next_selector": "a[rel='next']"},
                discovery_evidence_json={
                    "source_page": response.url,
                    "anchor_text": label,
                    "matched_terms": matches,
                    "rank": rank,
                },
            )
            await self.repository.create_column(column)
            columns.append(column)
        if columns:
            candidate.status = "columns_discovered"
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="column_discovery",
                    from_status="validated",
                    to_status="columns_discovered",
                    message="Same-site official-information columns were discovered.",
                    details_json={"column_count": len(columns)},
                )
            )
            await self.repository.commit()
        return columns

    async def _trial_crawl_column(
        self,
        run: SourceDiscoveryRun,
        candidate: SourceCandidate,
        column: SourceCandidateColumn,
    ) -> TrialStats:
        try:
            listing = await self.fetcher.fetch(column.column_url)
            soup = BeautifulSoup(listing.text, "lxml")
            base_host = (urlsplit(listing.url).hostname or "").lower().rstrip(".")
            detail_urls: list[str] = []
            seen: set[str] = set()
            for element in soup.select("a[href]"):
                if not isinstance(element, Tag):
                    continue
                href = element.get("href")
                if not isinstance(href, str):
                    continue
                try:
                    url = normalize_url(href, base_url=listing.url)
                except ValueError:
                    continue
                host = (urlsplit(url).hostname or "").lower().rstrip(".")
                if not host or not _same_site(base_host, host) or url in seen:
                    continue
                if url == normalize_url(column.column_url):
                    continue
                path = urlsplit(url).path.lower()
                if path.endswith(tuple(_DETAIL_EXTENSIONS)):
                    continue
                seen.add(url)
                detail_urls.append(url)
                if len(detail_urls) >= self.settings.source_discovery_trial_max_documents:
                    break
            if not detail_urls:
                stats = TrialStats(0, 0, 0, 1, 0)
                column.trial_discovered_count = 0
                column.trial_fetched_count = 0
                column.trial_success_count = 0
                column.trial_failed_count = 1
                column.trial_average_chars = 0
                column.quality_score = Decimal("0")
                column.status = "failed"
                column.error_message = "NO_DETAIL_LINKS"
                await self.repository.add_event(
                    SourceDiscoveryEvent(
                        run_id=run.id,
                        candidate_id=candidate.id,
                        stage="trial_crawl",
                        from_status="columns_discovered",
                        to_status="failed",
                        message="Trial crawl found no distinct same-site detail links.",
                        details_json={
                            "column_id": column.id,
                            "error_code": "NO_DETAIL_LINKS",
                            "discovered": 0,
                            "fetched": 0,
                            "success": 0,
                            "failed": 1,
                        },
                    )
                )
                await self.repository.commit()
                return stats
            success = 0
            failed = 0
            chars: list[int] = []
            content_selector = column.selectors_json.get("content")
            if not isinstance(content_selector, str) or not content_selector.strip():
                content_selector = "article, main, [role='main'], .content, #content"
            for detail_url in detail_urls:
                try:
                    response = await self.fetcher.fetch(detail_url)
                    parsed = BeautifulSoup(response.text, "lxml")
                    for node in parsed.select(
                        "script, style, noscript, nav, header, footer, aside, form"
                    ):
                        node.decompose()
                    content_nodes = parsed.select(content_selector)
                    texts = [node.get_text(" ", strip=True) for node in content_nodes]
                    text = max(texts, key=len, default="")
                    if len(
                        text
                    ) < self.settings.source_discovery_trial_min_chars or not _topic_matches(
                        text, run.topic
                    ):
                        failed += 1
                        continue
                    success += 1
                    chars.append(len(text))
                except Exception:
                    failed += 1
            stats = TrialStats(
                discovered=len(detail_urls),
                fetched=len(detail_urls),
                success=success,
                failed=failed,
                average_chars=round(sum(chars) / len(chars)) if chars else 0,
            )
            column.trial_discovered_count = stats.discovered
            column.trial_fetched_count = stats.fetched
            column.trial_success_count = stats.success
            column.trial_failed_count = stats.failed
            column.trial_average_chars = stats.average_chars
            ratio = stats.success / stats.fetched if stats.fetched else 0.0
            richness = min(
                stats.average_chars / max(self.settings.source_discovery_trial_min_chars * 2, 1),
                1.0,
            )
            column.quality_score = Decimal(str(round(0.5 * ratio + 0.5 * richness, 4)))
            column.status = "trial_crawled" if stats.success else "failed"
            column.error_message = None if stats.success else "NO_RELEVANT_DETAIL_DOCUMENTS"
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="trial_crawl",
                    from_status="columns_discovered",
                    to_status=column.status,
                    message="Trial crawl completed with bounded fetch and quality statistics.",
                    details_json={
                        "column_id": column.id,
                        "discovered": stats.discovered,
                        "fetched": stats.fetched,
                        "success": stats.success,
                        "failed": stats.failed,
                        "average_chars": stats.average_chars,
                        "content_selector": content_selector,
                        "topic_relevance_required": True,
                    },
                )
            )
            await self.repository.commit()
            return stats
        except Exception as exc:
            await self.repository.rollback()
            current = await self.repository.list_candidate_columns(candidate.id)
            current_column = next((item for item in current if item.id == column.id), column)
            current_column.status = "failed"
            current_column.error_message = exc.__class__.__name__
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="trial_crawl",
                    from_status="columns_discovered",
                    to_status="failed",
                    message="Trial crawl failed; exception details are recorded by type only.",
                    details_json={"column_id": column.id, "error_type": exc.__class__.__name__},
                )
            )
            await self.repository.commit()
            return TrialStats(0, 0, 0, 1, 0)

    async def _score_candidate(
        self,
        run: SourceDiscoveryRun,
        candidate: SourceCandidate,
        columns: list[SourceCandidateColumn],
    ) -> None:
        trial_document_count = sum(column.trial_discovered_count for column in columns)
        trial_success_count = sum(column.trial_success_count for column in columns)
        trial_failed_count = sum(column.trial_failed_count for column in columns)
        average_chars = round(
            sum(column.trial_average_chars for column in columns if column.trial_average_chars)
            / max(sum(bool(column.trial_average_chars) for column in columns), 1)
        )
        trial_ratio = trial_success_count / max(trial_document_count, 1)
        official_component = float(candidate.official_score or 0)
        column_component = min(len(columns) / 2.0, 1.0)
        richness_component = min(
            average_chars / max(self.settings.source_discovery_trial_min_chars * 2, 1), 1.0
        )
        quality = round(
            0.35 * official_component
            + 0.15 * column_component
            + 0.25 * trial_ratio
            + 0.25 * richness_component,
            4,
        )
        candidate.trial_column_count = len(columns)
        candidate.trial_document_count = trial_document_count
        candidate.trial_success_count = trial_success_count
        candidate.trial_failed_count = trial_failed_count
        candidate.trial_average_chars = average_chars
        candidate.quality_score = Decimal(str(quality))
        candidate.quality_breakdown_json = {
            "official_component": official_component,
            "column_component": column_component,
            "trial_success_ratio": trial_ratio,
            "content_richness_component": richness_component,
            "formula": "0.35*official + 0.15*columns + 0.25*trial_success + 0.25*richness",
            "threshold": self.settings.source_discovery_quality_threshold,
        }
        if quality >= self.settings.source_discovery_quality_threshold:
            candidate.status = "pending_approval"
            candidate.rejection_reason = None
        else:
            candidate.status = "rejected"
            candidate.rejection_reason = "QUALITY_SCORE_BELOW_THRESHOLD"
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=run.id,
                candidate_id=candidate.id,
                stage="quality_scoring",
                from_status="columns_discovered",
                to_status=candidate.status,
                message=(
                    "Candidate quality was calculated from official evidence and "
                    "trial-crawl data."
                ),
                details_json={
                    "quality_score": quality,
                    "threshold": self.settings.source_discovery_quality_threshold,
                    "trial_document_count": trial_document_count,
                },
            )
        )
        await self.repository.commit()

    async def get_run(self, run_id: int) -> SourceDiscoveryRun:
        run = await self.repository.get_run(run_id)
        if run is None:
            raise NotFoundError("SourceDiscoveryRun", run_id)
        return run

    async def get_candidate(self, candidate_id: int) -> SourceCandidate:
        candidate = await self.repository.get_candidate(candidate_id)
        if candidate is None:
            raise NotFoundError("SourceCandidate", candidate_id)
        return candidate

    async def approve(self, candidate_id: int, reviewer: str) -> SourceCandidate:
        candidate = await self.get_candidate(candidate_id)
        if candidate.status == "activated":
            return candidate
        if candidate.status != "pending_approval":
            raise AppError(
                "INVALID_SOURCE_CANDIDATE_STATE",
                "Only candidates awaiting manual approval can be approved",
                status_code=409,
                details={"candidate_id": candidate_id, "status": candidate.status},
            )
        approved = await self.repository.approve_candidate(candidate_id, reviewer)
        if approved is None:
            raise ConflictError("Candidate approval was claimed by another reviewer")
        run = await self.repository.refresh_run_counts(approved.run_id)
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=approved.run_id,
                candidate_id=approved.id,
                stage="manual_approval",
                from_status="pending_approval",
                to_status="approved",
                message="Candidate was manually approved by an authenticated administrator.",
                details_json={"reviewer": reviewer},
            )
        )
        await self.repository.save_run(run)
        return approved

    async def reject(self, candidate_id: int, reviewer: str, reason: str | None) -> SourceCandidate:
        if not reason or not reason.strip():
            raise AppError(
                "REJECTION_REASON_REQUIRED",
                "A reason is required when rejecting a source candidate",
                status_code=422,
            )
        candidate = await self.get_candidate(candidate_id)
        if candidate.status == "activated":
            raise AppError(
                "INVALID_SOURCE_CANDIDATE_STATE",
                "An activated source cannot be rejected",
                status_code=409,
            )
        rejected = await self.repository.reject_candidate(candidate_id, reviewer, reason.strip())
        if rejected is None:
            raise ConflictError("Candidate is not awaiting approval")
        run = await self.repository.refresh_run_counts(rejected.run_id)
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=rejected.run_id,
                candidate_id=rejected.id,
                stage="manual_approval",
                from_status=candidate.status,
                to_status="rejected",
                message="Candidate was manually rejected by an authenticated administrator.",
                details_json={"reviewer": reviewer, "reason": reason.strip()},
            )
        )
        await self.repository.save_run(run)
        return rejected

    async def activate(self, candidate_id: int) -> SourceCandidate:
        candidate = await self.get_candidate(candidate_id)
        if candidate.status == "activated":
            return candidate
        claimed = await self.repository.claim_candidate_activation(candidate_id)
        if claimed is None:
            current = await self.get_candidate(candidate_id)
            raise AppError(
                "INVALID_SOURCE_CANDIDATE_STATE",
                "Only manually approved candidates can be activated",
                status_code=409,
                details={"candidate_id": candidate_id, "status": current.status},
            )
        candidate = claimed
        try:
            columns = await self.repository.list_candidate_columns(candidate.id)
            if not columns:
                raise AppError(
                    "SOURCE_ACTIVATION_FAILED",
                    "Candidate has no discovered columns",
                    status_code=409,
                )
            run = await self.get_run(candidate.run_id)
            source = Source(
                source_key=f"discovered-{candidate.id}",
                name=candidate.name[:255],
                domain=candidate.domain,
                region=run.region,
                organization_level=run.organization_level,
                organization_type="government",
                official_status="official",
                homepage_url=candidate.validation_final_url or candidate.canonical_homepage_url,
                enabled=True,
                priority=0,
                crawl_frequency="daily",
            )
            source.columns.extend(
                [
                    SourceColumn(
                        column_key=column.column_key,
                        column_name=column.column_name,
                        column_url=column.column_url,
                        parser_type=column.parser_type,
                        enabled=True,
                        max_pages=100,
                        request_interval_seconds=1,
                        selectors_json=column.selectors_json,
                        pagination_json=column.pagination_json,
                    )
                    for column in columns
                    if column.status == "trial_crawled"
                ]
            )
            if not source.columns:
                raise AppError(
                    "SOURCE_ACTIVATION_FAILED",
                    "No trial-crawled column passed quality checks",
                    status_code=409,
                )
            self.repository.session.add(source)
            await self.repository.session.flush()
            candidate.source_id = source.id
            candidate.status = "activated"
            candidate.approved_at = candidate.approved_at or datetime.now(UTC)
            run = await self.repository.refresh_run_counts(run.id)
            run.status = "activated"
            await self.repository.add_event(
                SourceDiscoveryEvent(
                    run_id=run.id,
                    candidate_id=candidate.id,
                    stage="source_activation",
                    from_status="activating",
                    to_status="activated",
                    message="Approved candidate was materialized as an enabled source and columns.",
                    details_json={"source_id": source.id, "column_count": len(source.columns)},
                )
            )
            await self.repository.save_run(run)
            return candidate
        except IntegrityError as exc:
            await self._mark_activation_failed(candidate_id, "SOURCE_KEY_CONFLICT")
            raise ConflictError("Source activation conflicts with an existing source") from exc
        except AppError as exc:
            await self._mark_activation_failed(candidate_id, exc.code)
            raise
        except Exception as exc:
            await self._mark_activation_failed(candidate_id, exc.__class__.__name__)
            raise AppError(
                "SOURCE_ACTIVATION_FAILED",
                "Source activation failed after the candidate claim",
                status_code=503,
                details={"error_type": exc.__class__.__name__},
            ) from exc

    async def _mark_activation_failed(self, candidate_id: int, reason: str) -> None:
        await self.repository.rollback()
        failed_candidate = await self.repository.get_candidate(candidate_id)
        if failed_candidate is None:
            return
        failed_candidate.status = "failed"
        failed_candidate.rejection_reason = f"ACTIVATION_FAILED:{reason}"
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=failed_candidate.run_id,
                candidate_id=failed_candidate.id,
                stage="source_activation_failure",
                from_status="activating",
                to_status="failed",
                message="Source activation failed after the candidate was claimed.",
                details_json={"error_type": reason},
            )
        )
        await self.repository.commit()

    async def retry(self, run_id: int) -> SourceDiscoveryRun:
        run = await self.get_run(run_id)
        if run.status != "failed":
            raise AppError(
                "INVALID_SOURCE_DISCOVERY_STATE",
                "Only failed discovery runs can be retried",
                status_code=409,
                details={"run_id": run_id, "status": run.status},
            )
        run.status = "pending"
        run.started_at = None
        run.finished_at = None
        run.error_message = None
        await self.repository.save_run(run)
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=run.id,
                stage="retry",
                from_status="failed",
                to_status="pending",
                message="Failed discovery run was requeued for another bounded attempt.",
                details_json={},
            )
        )
        await self.repository.commit()
        return run

    async def mark_queue_failure(self, run_id: int, error_type: str) -> SourceDiscoveryRun:
        run = await self.get_run(run_id)
        previous_status = run.status
        if run.status != "pending":
            return run
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        run.error_message = f"QUEUE_UNAVAILABLE:{error_type}"
        await self.repository.add_event(
            SourceDiscoveryEvent(
                run_id=run.id,
                stage="queue_failure",
                from_status=previous_status,
                to_status="failed",
                message="Discovery run could not be submitted to the task queue.",
                details_json={"error_type": error_type},
            )
        )
        await self.repository.save_run(run)
        return run

    async def list_runs(self, *, limit: int = 100) -> list[SourceDiscoveryRun]:
        return await self.repository.list_runs(limit=limit)

    async def list_candidates(self, run_id: int) -> list[SourceCandidate]:
        await self.get_run(run_id)
        return await self.repository.list_candidates(run_id)

    async def candidate_detail(
        self, candidate_id: int
    ) -> tuple[SourceCandidate, list[SourceCandidateColumn], list[SourceDiscoveryEvent]]:
        candidate = await self.get_candidate(candidate_id)
        return (
            candidate,
            await self.repository.list_candidate_columns(candidate.id),
            await self.repository.list_events(run_id=candidate.run_id, candidate_id=candidate.id),
        )

    async def metrics(self) -> dict[str, object]:
        return await self.repository.metrics()


def build_source_discovery_service(
    repository: SourceDiscoveryRepository,
    settings: Settings,
    *,
    provider: CandidateDiscoveryProvider | None = None,
    fetcher: HttpFetcher | None = None,
) -> SourceDiscoveryService:
    return SourceDiscoveryService(repository, settings, provider=provider, fetcher=fetcher)


def _topic_matches(text: str, topic: str) -> bool:
    normalized_text = " ".join(text.lower().split())
    normalized_topic = " ".join(topic.lower().split())
    if not normalized_topic:
        return False
    if normalized_topic in normalized_text:
        return True
    tokens = [token for token in normalized_topic.split() if len(token) >= 2]
    if not tokens:
        return False
    required = (len(tokens) + 1) // 2
    return sum(token in normalized_text for token in tokens) >= required


def _build_query(topic: str, region: str | None, organization_level: str | None) -> str:
    parts = [topic.strip(), "官方 政府 网站"]
    if region:
        parts.append(region.strip())
    if organization_level:
        parts.append(organization_level.strip())
    return " ".join(part for part in parts if part)


def _trusted_suffix(host: str, suffixes: list[str]) -> str | None:
    normalized = host.lower().rstrip(".")
    for raw_suffix in suffixes:
        suffix = raw_suffix.strip().lower().lstrip(".").rstrip(".")
        if suffix and (normalized == suffix or normalized.endswith(f".{suffix}")):
            return f".{suffix}"
    return None


def _same_site(first: str, second: str) -> bool:
    a = first.lower().rstrip(".")
    b = second.lower().rstrip(".")
    return a == b or a.endswith(f".{b}") or b.endswith(f".{a}")


def _column_key(label: str, url: str, rank: int) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "-", label.strip().lower()).strip("-")
    if not normalized:
        normalized = f"column-{rank}"
    digest = hashlib.sha1(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:8]
    return f"{normalized[:110]}-{digest}"
