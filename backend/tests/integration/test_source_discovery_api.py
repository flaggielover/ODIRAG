from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import httpx

from app.crawler import HttpFetcher
from app.errors import AppError
from app.models import (
    Document,
    Source,
    SourceCandidate,
    SourceCandidateColumn,
    SourceDiscoveryRun,
)
from app.repositories.source_discovery import SourceDiscoveryRepository
from app.services.source_discovery import SourceDiscoveryService
from app.source_discovery import CandidateHit
from app.tasks.celery_app import celery_app


async def _public_addresses(_hostname: str) -> tuple[str, ...]:
    return ("93.184.216.34",)


@dataclass(slots=True)
class FixtureCandidateProvider:
    url: str = "https://agency.gov.cn/"
    name: str = "fixture-test"
    called: int = 0
    expected_query_term: str | None = "support"

    async def search(self, query: str, *, limit: int) -> list[CandidateHit]:
        self.called += 1
        if self.expected_query_term:
            assert self.expected_query_term in query.lower()
        assert limit > 0
        return [
            CandidateHit(
                url=self.url,
                title="Official policy agency",
                snippet="Official government support policy portal",
                rank=1,
            )
        ]


def _site_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/":
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><title>Government agency</title><body>"
                "<h1>Official Government Agency</h1>"
                '<a href="/policies/">Policy notices</a>'
                "</body></html>"
            ),
        )
    if path == "/policies/":
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html; charset=utf-8"},
            text=(
                "<html><body><h1>Policy notices</h1>"
                '<a href="/policies/support-2026.html">Software support notice</a>'
                "</body></html>"
            ),
        )
    if path == "/policies/support-2026.html":
        content = "Official government software support policy details. " * 20
        return httpx.Response(
            200,
            request=request,
            headers={"content-type": "text/html; charset=utf-8"},
            text=f"<html><body><h1>Support policy</h1><article>{content}</article></body></html>",
        )
    return httpx.Response(404, request=request)


async def test_source_discovery_requires_manual_approval_before_activation(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(_site_handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "region": "Sichuan",
                "required_source_count": 1,
                "required_document_count": 1,
                "execution_mode": "inline",
            },
        )

        assert created.status_code == 201, created.text
        run = created.json()
        assert run["gap_detected"] is True
        assert run["status"] == "awaiting_approval"
        assert provider.called == 1

        candidates = await client.get(
            f"/api/source-discovery/runs/{run['id']}/candidates", headers=auth_headers
        )
        assert candidates.status_code == 200, candidates.text
        candidate = candidates.json()[0]
        assert candidate["official_status"] == "official"
        assert candidate["status"] == "pending_approval"
        assert candidate["quality_score"] >= 0.65
        assert candidate["trial_success_count"] == 1
        assert candidate["columns"][0]["status"] == "trial_crawled"

        pending_metrics = await client.get("/api/source-discovery/metrics", headers=auth_headers)
        assert pending_metrics.json()["pending_approval_count"] == 1
        assert pending_metrics.json()["candidate_status_counts"]["pending_approval"] == 1
        assert pending_metrics.json()["run_status_counts"]["awaiting_approval"] == 1

        blocked = await client.post(
            f"/api/source-discovery/candidates/{candidate['id']}/activate",
            headers=auth_headers,
        )
        assert blocked.status_code == 409
        assert blocked.json()["error"]["code"] == "INVALID_SOURCE_CANDIDATE_STATE"

        approved = await client.post(
            f"/api/source-discovery/candidates/{candidate['id']}/approve",
            headers=auth_headers,
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"
        assert approved.json()["approved_by"] == "admin"

        activated = await client.post(
            f"/api/source-discovery/candidates/{candidate['id']}/activate",
            headers=auth_headers,
        )
        assert activated.status_code == 200, activated.text
        assert activated.json()["status"] == "activated"
        source_id = activated.json()["source_id"]
        assert source_id is not None

        source = await client.get(f"/api/sources/{source_id}", headers=auth_headers)
        assert source.status_code == 200, source.text
        assert source.json()["official_status"] == "official"
        assert source.json()["enabled"] is True
        assert source.json()["columns"][0]["enabled"] is True

        events = await client.get(
            f"/api/source-discovery/runs/{run['id']}/events", headers=auth_headers
        )
        stages = {event["stage"] for event in events.json()}
        assert {
            "content_gap_detection",
            "candidate_discovery",
            "official_status_validation",
            "column_discovery",
            "trial_crawl",
            "quality_scoring",
            "manual_approval",
            "source_activation",
        } <= stages

        metrics = await client.get("/api/source-discovery/metrics", headers=auth_headers)
        assert metrics.status_code == 200
        assert metrics.json()["activated_source_count"] == 1
        assert metrics.json()["candidate_status_counts"]["activated"] == 1
        assert metrics.json()["run_status_counts"]["activated"] == 1


async def test_jxt_software_policy_reaches_manual_gate_without_activation(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    requested_paths: list[str] = []
    redirected_detail = "/scjxt/ggtz/2026/8/6/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb.shtml"
    detail_pages = {
        (
            "/scjxt/ggtz/2026/8/10/fc4f8fb462504ef883ec09a03fba5916.shtml"
        ): "软件企业税收优惠政策核查结果公示",
        (
            "/scjxt/ggtz/2026/8/7/db7f01e777274f9b9004f35f2b34df5a.shtml"
        ): "软件首版次推广应用指导目录公示",
        (
            "/scjxt/wjfb/2026/1/6/8828cf46e72849dfa361dfae063c28fe.shtml"
        ): "关于组织申报工业软件研发项目的通知",
        (
            "/scjxt/zcjdn/2021/7/20/bccd0576a4514f199129866c3813433f.shtml"
        ): "软件首版次管理办法政策解读",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requested_paths.append(path)
        headers = {"content-type": "text/html; charset=utf-8"}
        if path == "/scjxt/index.shtml":
            return httpx.Response(
                200,
                request=request,
                headers=headers,
                text=(
                    "<html><body><h1>四川省人民政府 四川省经济和信息化厅</h1>"
                    '<a href="/scjxt/index.shtml">首页</a>'
                    '<a href="/scjxt/wjfb/common_list.shtml">通知</a>'
                    '<a href="/scjxt/zcjdn/common_listnb.shtml">政策解读</a>'
                    '<a href="/scjxt/ggtz/2026/8/5/'
                    'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.shtml">面板外软件政策新闻</a>'
                    '<div id="panel-20002">'
                    '<a href="/scjxt/ggtz/2026/8/10/'
                    'fc4f8fb462504ef883ec09a03fba5916.shtml">软件企业税惠公示</a>'
                    '<a href="/scjxt/ggtz/2026/8/7/'
                    'db7f01e777274f9b9004f35f2b34df5a.shtml">软件首版次公示</a>'
                    f'<a href="{redirected_detail}">工业软件政策通知</a>'
                    "</div>"
                    "</body></html>"
                ),
            )
        if path == redirected_detail:
            return httpx.Response(
                302,
                request=request,
                headers={"location": "https://public.example/redirected-policy"},
            )
        if request.url.host == "public.example":
            return httpx.Response(
                200,
                request=request,
                headers=headers,
                text=(
                    '<html><head><meta name="ArticleTitle" content="工业软件政策通知">'
                    '</head><body><div id="NewsContent">'
                    f"{'工业软件产业支持政策。' * 20}"
                    "</div></body></html>"
                ),
            )
        listing_links = {
            "/scjxt/wjfb/common_list.shtml": next(
                path for path in detail_pages if "/wjfb/" in path
            ),
            "/scjxt/zcjdn/common_listnb.shtml": next(
                path for path in detail_pages if "/zcjdn/" in path
            ),
        }
        if path in listing_links:
            detail_path = listing_links[path]
            return httpx.Response(
                200,
                request=request,
                headers=headers,
                text=(
                    "<html><body><nav>"
                    '<a href="/scjxt/index.shtml">首页</a>'
                    '<a href="/scjxt/xwzx/news.shtml">新闻中心</a>'
                    "</nav>"
                    f'<a href="{detail_path}">{detail_pages[detail_path]}</a>'
                    "</body></html>"
                ),
            )
        if path in detail_pages:
            content = f"{detail_pages[path]}，支持四川省软件产业高质量发展。" * 12
            return httpx.Response(
                200,
                request=request,
                headers=headers,
                text=(
                    "<html><head><title>公告公示-四川省经济和信息化厅</title>"
                    f'<meta name="ArticleTitle" content="{detail_pages[path]}">'
                    '<meta name="PubDate" content="2026-08-10">'
                    "</head>"
                    f'<body><div id="NewsContent">{content}</div></body></html>'
                ),
            )
        return httpx.Response(404, request=request)

    provider = FixtureCandidateProvider(
        url="https://jxt.sc.gov.cn/scjxt/index.shtml",
        expected_query_term=None,
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "四川省软件产业政策",
                "required_source_count": 10,
                "required_document_count": 10,
                "max_candidates": 1,
                "execution_mode": "inline",
            },
        )

    assert created.status_code == 201, created.text
    assert created.json()["status"] == "awaiting_approval"
    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates",
        headers=auth_headers,
    )
    candidate = candidates.json()[0]
    assert candidate["status"] == "pending_approval"
    assert candidate["quality_score"] >= 0.65
    assert candidate["trial_success_count"] >= 1
    assert candidate["trial_failed_count"] >= 1
    assert all("/2026/" not in column["column_url"] for column in candidate["columns"])
    embedded = next(
        column
        for column in candidate["columns"]
        if column["column_url"] == "https://jxt.sc.gov.cn/scjxt/index.shtml"
    )
    assert embedded["selectors_json"]["list_link"] == "#panel-20002 a[href]"
    assert embedded["discovery_evidence_json"]["discovery_method"] == "embedded_list_panel"
    assert "/scjxt/ggtz/2026/8/5/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.shtml" not in requested_paths
    events = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/events",
        headers=auth_headers,
    )
    trial_events = [event for event in events.json() if event["stage"] == "trial_crawl"]
    assert any(
        event["details_json"].get("rejection_counts", {}).get("CROSS_HOST_REDIRECT") == 1
        for event in trial_events
    )

    blocked = await client.post(
        f"/api/source-discovery/candidates/{candidate['id']}/activate",
        headers=auth_headers,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "INVALID_SOURCE_CANDIDATE_STATE"


async def test_source_discovery_stops_when_database_coverage_has_no_gap(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider()
    app.state.source_discovery_provider = provider
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="coverage-source",
            name="Coverage source",
            domain="coverage.gov.cn",
            region="Sichuan",
            homepage_url="https://coverage.gov.cn/",
            official_status="official",
            enabled=True,
        )
        session.add(source)
        await session.flush()
        session.add(
            Document(
                document_id="coverage-document",
                source_id=source.id,
                title="Existing support policy",
                source_url="https://coverage.gov.cn/support",
                canonical_url="https://coverage.gov.cn/support",
                content="Existing support policy content",
                region="Sichuan",
                final_status="approved",
                index_status="pending",
            )
        )
        session.add(
            Source(
                source_key="unrelated-coverage-source",
                name="Unrelated coverage source",
                domain="unrelated.gov.cn",
                region="Sichuan",
                homepage_url="https://unrelated.gov.cn/",
                official_status="official",
                enabled=True,
            )
        )
        await session.commit()

    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={
            "topic": "support",
            "region": "Sichuan",
            "required_source_count": 1,
            "required_document_count": 1,
            "execution_mode": "inline",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["status"] == "no_gap"
    assert created.json()["gap_detected"] is False
    assert created.json()["existing_source_count"] == 1
    assert created.json()["existing_document_count"] == 1
    assert provider.called == 0


async def test_source_discovery_rejects_blank_topic(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={"topic": "   ", "execution_mode": "inline"},
    )

    assert created.status_code == 422


async def test_source_discovery_ignores_matching_documents_from_disabled_sources(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider()
    app.state.source_discovery_provider = provider
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="retired-coverage-source",
            name="Retired coverage source",
            domain="retired.gov.cn",
            region="Sichuan",
            homepage_url="https://retired.gov.cn/",
            official_status="official",
            enabled=False,
        )
        session.add(source)
        await session.flush()
        session.add(
            Document(
                document_id="retired-coverage-document",
                source_id=source.id,
                title="Existing support policy",
                source_url="https://retired.gov.cn/support",
                canonical_url="https://retired.gov.cn/support",
                content="Existing support policy content",
                region="Sichuan",
                final_status="approved",
                index_status="pending",
            )
        )
        await session.commit()

    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={
            "topic": "support",
            "region": "Sichuan",
            "required_source_count": 1,
            "required_document_count": 1,
            "execution_mode": "inline",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["gap_detected"] is True
    assert created.json()["existing_source_count"] == 0
    assert created.json()["existing_document_count"] == 0
    assert provider.called == 1


async def test_source_discovery_treats_topic_wildcards_as_literals(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider(expected_query_term=None)
    app.state.source_discovery_provider = provider
    async with app.state.database.session_factory() as session:
        source = Source(
            source_key="wildcard-source",
            name="Wildcard source",
            domain="wildcard.gov.cn",
            homepage_url="https://wildcard.gov.cn/",
            official_status="official",
            enabled=True,
        )
        session.add(source)
        await session.flush()
        session.add(
            Document(
                document_id="wildcard-document",
                source_id=source.id,
                title="Ordinary policy",
                source_url="https://wildcard.gov.cn/policy",
                canonical_url="https://wildcard.gov.cn/policy",
                content="Ordinary policy content without a percent character",
                final_status="approved",
                index_status="pending",
            )
        )
        await session.commit()

    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={
            "topic": "%",
            "required_source_count": 1,
            "required_document_count": 1,
            "execution_mode": "inline",
        },
    )

    assert created.status_code == 201, created.text
    assert created.json()["gap_detected"] is True
    assert created.json()["existing_source_count"] == 0
    assert created.json()["existing_document_count"] == 0
    assert provider.called == 1


async def test_source_discovery_does_not_promote_unverified_domain(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider(url="https://example.com/")
    async with httpx.AsyncClient(transport=httpx.MockTransport(_site_handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )

    assert created.status_code == 201, created.text
    assert created.json()["status"] == "failed"
    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates", headers=auth_headers
    )
    assert candidates.json()[0]["status"] == "validation_failed"
    assert candidates.json()[0]["official_status"] == "unverified"
    assert candidates.json()[0]["source_id"] is None
    metrics = await client.get("/api/source-discovery/metrics", headers=auth_headers)
    assert metrics.json()["run_status_counts"]["failed"] == 1
    assert metrics.json()["candidate_status_counts"]["validation_failed"] == 1


async def test_source_discovery_requires_https_for_official_status(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    provider = FixtureCandidateProvider(url="http://agency.gov.cn/")
    async with httpx.AsyncClient(transport=httpx.MockTransport(_site_handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )

    assert created.status_code == 201, created.text
    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates",
        headers=auth_headers,
    )
    candidate = candidates.json()[0]
    assert candidate["status"] == "validation_failed"
    assert candidate["official_status"] == "unverified"
    assert candidate["official_evidence_json"]["https"] is False


async def test_source_discovery_rejects_redirect_to_sibling_host(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    """A trusted suffix is not enough when the homepage changes host."""

    def redirect_handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "agency.gov.cn":
            return httpx.Response(
                302,
                request=request,
                headers={"location": "https://sub.agency.gov.cn/"},
            )
        if request.url.host == "sub.agency.gov.cn":
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><body><h1>Official government agency</h1></body></html>",
            )
        return httpx.Response(404, request=request)

    provider = FixtureCandidateProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(redirect_handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )

    assert created.status_code == 201, created.text
    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates",
        headers=auth_headers,
    )
    candidate = candidates.json()[0]
    assert candidate["status"] == "validation_failed"
    assert candidate["official_status"] == "unverified"
    assert candidate["official_evidence_json"]["same_site"] is True
    assert candidate["official_evidence_json"]["same_host"] is False


async def test_trial_crawl_rejects_column_without_detail_links(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                request=request,
                text=(
                    "<html><body><h1>Official Government Agency</h1>"
                    '<a href="/policies/">Policy notices</a></body></html>'
                ),
            )
        if request.url.path == "/policies/":
            return httpx.Response(
                200,
                request=request,
                text=f"<html><body><nav>{'Navigation ' * 200}</nav></body></html>",
            )
        return httpx.Response(404, request=request)

    provider = FixtureCandidateProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )

    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates",
        headers=auth_headers,
    )
    column = candidates.json()[0]["columns"][0]
    assert column["status"] == "failed"
    assert column["error_message"] == "NO_DETAIL_LINKS"
    assert column["trial_success_count"] == 0


async def test_trial_crawl_rejects_unrelated_long_detail_page(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/":
            return httpx.Response(
                200,
                request=request,
                text=(
                    "<html><body><h1>Official Government Agency</h1>"
                    '<a href="/policies/">Policy notices</a></body></html>'
                ),
            )
        if request.url.path == "/policies/":
            return httpx.Response(
                200,
                request=request,
                text='<html><body><a href="/about.html">About the agency</a></body></html>',
            )
        if request.url.path == "/about.html":
            return httpx.Response(
                200,
                request=request,
                text=f"<html><main>{'Contact directory and office hours. ' * 30}</main></html>",
            )
        return httpx.Response(404, request=request)

    provider = FixtureCandidateProvider()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as site_client:
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )

    candidates = await client.get(
        f"/api/source-discovery/runs/{created.json()['id']}/candidates",
        headers=auth_headers,
    )
    column = candidates.json()[0]["columns"][0]
    assert column["status"] == "failed"
    assert column["error_message"] == "NO_RELEVANT_DETAIL_DOCUMENTS"
    assert column["trial_success_count"] == 0


async def test_source_discovery_reports_missing_live_provider_credentials(
    client: httpx.AsyncClient, auth_headers: dict[str, str]
) -> None:
    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={
            "topic": "provider-credential-gap",
            "required_source_count": 10,
            "required_document_count": 10,
            "execution_mode": "inline",
        },
    )

    assert created.status_code == 503
    assert created.json()["error"]["code"] == "PROVIDER_UNAVAILABLE"
    assert created.json()["error"]["details"]["provider"] == "brave-source-discovery"
    runs = await client.get("/api/source-discovery/runs", headers=auth_headers)
    failed = next(run for run in runs.json() if run["topic"] == "provider-credential-gap")
    assert failed["status"] == "failed"
    assert failed["error_message"] == "ProviderUnavailableError"


async def test_queue_failure_is_persisted_and_retryable(
    client: httpx.AsyncClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    def fail_queue(*_args, **_kwargs) -> None:
        raise ConnectionError("fixture queue outage")

    monkeypatch.setattr(celery_app, "send_task", fail_queue)
    created = await client.post(
        "/api/source-discovery/runs",
        headers=auth_headers,
        json={
            "topic": "queue-failure-gap",
            "required_source_count": 10,
            "required_document_count": 10,
            "execution_mode": "queued",
        },
    )

    assert created.status_code == 503
    runs = await client.get("/api/source-discovery/runs", headers=auth_headers)
    failed = next(run for run in runs.json() if run["topic"] == "queue-failure-gap")
    assert failed["status"] == "failed"
    assert failed["error_message"] == "QUEUE_UNAVAILABLE:ConnectionError"
    events = await client.get(
        f"/api/source-discovery/runs/{failed['id']}/events", headers=auth_headers
    )
    assert any(event["stage"] == "queue_failure" for event in events.json())

    monkeypatch.setattr(celery_app, "send_task", lambda *_args, **_kwargs: None)
    retried = await client.post(
        f"/api/source-discovery/runs/{failed['id']}/retry", headers=auth_headers
    )
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "pending"


async def test_retry_reuses_candidate_without_unique_constraint_dead_end(
    app, client: httpx.AsyncClient, auth_headers: dict[str, str], monkeypatch
) -> None:
    provider = FixtureCandidateProvider()
    mode = {"columns": False}

    def changing_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/" and not mode["columns"]:
            return httpx.Response(
                200,
                request=request,
                headers={"content-type": "text/html; charset=utf-8"},
                text="<html><body><h1>Official Government Agency</h1></body></html>",
            )
        return _site_handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(changing_handler)) as site_client:
        fetcher = HttpFetcher(
            client=site_client,
            resolver=_public_addresses,
            timeout_seconds=1,
            max_bytes=1024 * 1024,
        )
        app.state.source_discovery_provider = provider
        app.state.source_discovery_fetcher = fetcher
        created = await client.post(
            "/api/source-discovery/runs",
            headers=auth_headers,
            json={
                "topic": "support",
                "required_source_count": 10,
                "required_document_count": 10,
                "execution_mode": "inline",
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["status"] == "failed"
        run_id = created.json()["id"]
        initial_candidates = await client.get(
            f"/api/source-discovery/runs/{run_id}/candidates", headers=auth_headers
        )
        candidate_id = initial_candidates.json()[0]["id"]

        monkeypatch.setattr(celery_app, "send_task", lambda *_args, **_kwargs: None)
        retried = await client.post(
            f"/api/source-discovery/runs/{run_id}/retry", headers=auth_headers
        )
        assert retried.status_code == 200, retried.text
        mode["columns"] = True
        async with app.state.database.session_factory() as session:
            service = SourceDiscoveryService(
                SourceDiscoveryRepository(session),
                app.state.settings,
                provider=provider,
                fetcher=fetcher,
            )
            rerun = await service.execute(run_id)
        assert rerun.status == "awaiting_approval"

    candidates = await client.get(
        f"/api/source-discovery/runs/{run_id}/candidates", headers=auth_headers
    )
    assert len(candidates.json()) == 1
    assert candidates.json()[0]["id"] == candidate_id
    assert candidates.json()[0]["status"] == "pending_approval"
    assert len(candidates.json()[0]["columns"]) == 1


async def test_activation_exception_is_compensated_to_failed_state(app, monkeypatch) -> None:
    async with app.state.database.session_factory() as session:
        repository = SourceDiscoveryRepository(session)
        run = await repository.create_run(
            SourceDiscoveryRun(
                topic="activation failure",
                query_text="activation failure official government site",
                gap_evidence_json={"gap_detected": True},
                status="awaiting_approval",
                discovery_provider="fixture-test",
                max_candidates=1,
            )
        )
        candidate = await repository.create_candidate(
            SourceCandidate(
                run_id=run.id,
                canonical_homepage_url="https://activation.gov.cn/",
                domain="activation.gov.cn",
                name="Activation fixture",
                discovery_provider="fixture-test",
                discovery_query=run.query_text,
                official_status="official",
                official_score=Decimal("1"),
                official_evidence_json={"trusted_suffix": ".gov.cn"},
                status="approved",
                quality_score=Decimal("1"),
            )
        )
        await repository.create_column(
            SourceCandidateColumn(
                candidate_id=candidate.id,
                column_key="policies-fixture",
                column_name="Policies",
                column_url="https://activation.gov.cn/policies/",
                selectors_json={
                    "list_link": "a[href]",
                    "title": "h1",
                    "content": "article",
                },
                pagination_json={},
                discovery_evidence_json={},
                status="trial_crawled",
                trial_discovered_count=1,
                trial_fetched_count=1,
                trial_success_count=1,
                quality_score=Decimal("1"),
            )
        )
        run_id = run.id
        candidate_id = candidate.id
        await repository.commit()
        service = SourceDiscoveryService(
            repository,
            app.state.settings,
            provider=FixtureCandidateProvider(),
        )

        async def fail_after_source_flush(_run_id: int) -> None:
            raise RuntimeError("fixture activation failure")

        monkeypatch.setattr(repository, "refresh_run_counts", fail_after_source_flush)
        try:
            await service.activate(candidate_id)
            raise AssertionError("activation should have failed")
        except AppError as exc:
            assert exc.code == "SOURCE_ACTIVATION_FAILED"
            assert exc.details == {"error_type": "RuntimeError"}

        failed = await repository.get_candidate(candidate_id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.source_id is None
        assert failed.rejection_reason == "ACTIVATION_FAILED:RuntimeError"
        events = await repository.list_events(run_id=run_id, candidate_id=candidate_id)
        assert any(
            event.stage == "source_activation_failure" and event.to_status == "failed"
            for event in events
        )

        no_column_candidate = await repository.create_candidate(
            SourceCandidate(
                run_id=run_id,
                canonical_homepage_url="https://no-columns.gov.cn/",
                domain="no-columns.gov.cn",
                name="No columns fixture",
                discovery_provider="fixture-test",
                discovery_query="activation failure official government site",
                official_status="official",
                official_score=Decimal("1"),
                official_evidence_json={"trusted_suffix": ".gov.cn"},
                status="approved",
                quality_score=Decimal("1"),
            )
        )
        no_column_candidate_id = no_column_candidate.id
        await repository.commit()
        try:
            await service.activate(no_column_candidate_id)
            raise AssertionError("activation without columns should have failed")
        except AppError as exc:
            assert exc.code == "SOURCE_ACTIVATION_FAILED"
            assert exc.status_code == 409

        failed_without_columns = await repository.get_candidate(no_column_candidate_id)
        assert failed_without_columns is not None
        assert failed_without_columns.status == "failed"
        assert (
            failed_without_columns.rejection_reason == "ACTIVATION_FAILED:SOURCE_ACTIVATION_FAILED"
        )
        no_column_events = await repository.list_events(
            run_id=run_id, candidate_id=no_column_candidate_id
        )
        assert any(
            event.stage == "source_activation_failure" and event.to_status == "failed"
            for event in no_column_events
        )
