from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Depends, Query, Response, status

from app.config import Settings
from app.crawler import CozeCrawlProvider
from app.dependencies import AdminUser, DatabaseSession, get_app_settings
from app.repositories.sources import SourceRepository
from app.schemas.source import (
    CozeConnectionResponse,
    SourceCreate,
    SourceResponse,
    SourceTestResponse,
    SourceUpdate,
)
from app.services.sources import SourceService

router = APIRouter(prefix="/sources", tags=["sources"])


def get_source_service(
    session: DatabaseSession,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> SourceService:
    return SourceService(
        SourceRepository(session),
        timeout_seconds=settings.crawler_timeout_seconds,
        max_bytes=min(settings.max_download_bytes, 256 * 1024),
        max_redirects=settings.crawler_max_redirects,
    )


SourceServiceDependency = Annotated[SourceService, Depends(get_source_service)]


@router.get("", response_model=list[SourceResponse])
async def list_sources(
    _admin: AdminUser,
    service: SourceServiceDependency,
    enabled: Annotated[bool | None, Query()] = None,
) -> list[SourceResponse]:
    return [SourceResponse.model_validate(source) for source in await service.list(enabled=enabled)]


@router.post("", response_model=SourceResponse, status_code=status.HTTP_201_CREATED)
async def create_source(
    payload: SourceCreate, _admin: AdminUser, service: SourceServiceDependency
) -> SourceResponse:
    return SourceResponse.model_validate(await service.create(payload))


@router.get("/{source_id}", response_model=SourceResponse)
async def get_source(
    source_id: int, _admin: AdminUser, service: SourceServiceDependency
) -> SourceResponse:
    return SourceResponse.model_validate(await service.get(source_id))


@router.put("/{source_id}", response_model=SourceResponse)
async def update_source(
    source_id: int,
    payload: SourceUpdate,
    _admin: AdminUser,
    service: SourceServiceDependency,
) -> SourceResponse:
    return SourceResponse.model_validate(await service.update(source_id, payload))


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(
    source_id: int, _admin: AdminUser, service: SourceServiceDependency
) -> Response:
    await service.delete(source_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{source_id}/test", response_model=SourceTestResponse)
async def test_source(
    source_id: int, _admin: AdminUser, service: SourceServiceDependency
) -> SourceTestResponse:
    return await service.test(source_id)


@router.post("/{source_id}/test-local", response_model=SourceTestResponse)
async def test_source_local(
    source_id: int, _admin: AdminUser, service: SourceServiceDependency
) -> SourceTestResponse:
    return await service.test(source_id)


@router.post("/{source_id}/connectivity-tests/local", response_model=SourceTestResponse)
async def diagnose_source_local(
    source_id: int, _admin: AdminUser, service: SourceServiceDependency
) -> SourceTestResponse:
    return await service.test(source_id)


@router.post("/{source_id}/test-coze", response_model=CozeConnectionResponse)
async def test_source_coze(
    source_id: int,
    _admin: AdminUser,
    service: SourceServiceDependency,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CozeConnectionResponse:
    source = await service.get(source_id)
    return await _test_coze_contract(
        source_id,
        cast(Literal["legacy_single_article", "batch_crawl"], source.coze_contract_mode),
        service=service,
        settings=settings,
    )


@router.post("/{source_id}/connectivity-tests/coze", response_model=CozeConnectionResponse)
async def test_source_coze_preferred(
    source_id: int,
    _admin: AdminUser,
    service: SourceServiceDependency,
    settings: Annotated[Settings, Depends(get_app_settings)],
    contract: Annotated[Literal["legacy_single_article", "batch_crawl"] | None, Query()] = None,
) -> CozeConnectionResponse:
    source = await service.get(source_id)
    return await _test_coze_contract(
        source_id,
        contract
        or cast(Literal["legacy_single_article", "batch_crawl"], source.coze_contract_mode),
        service=service,
        settings=settings,
    )


@router.post(
    "/{source_id}/connectivity-tests/coze/{contract}",
    response_model=CozeConnectionResponse,
)
async def test_source_coze_contract(
    source_id: int,
    contract: str,
    _admin: AdminUser,
    service: SourceServiceDependency,
    settings: Annotated[Settings, Depends(get_app_settings)],
) -> CozeConnectionResponse:
    if contract in {"legacy", "legacy_single_article"}:
        normalized_contract: Literal["legacy_single_article", "batch_crawl"] = (
            "legacy_single_article"
        )
    elif contract in {"batch", "batch_crawl"}:
        normalized_contract = "batch_crawl"
    else:
        from app.errors import AppError

        raise AppError("INVALID_COZE_CONTRACT", "Unsupported Coze contract", status_code=422)
    return await _test_coze_contract(
        source_id, normalized_contract, service=service, settings=settings
    )


async def _test_coze_contract(
    source_id: int,
    contract: Literal["legacy_single_article", "batch_crawl"],
    *,
    service: SourceService,
    settings: Settings,
) -> CozeConnectionResponse:
    source = await service.get(source_id)
    checked_at = datetime.now(UTC)
    if not settings.coze_enabled:
        await service.record_coze_test(source_id, status="disabled", error_code="COZE_DISABLED")
        return CozeConnectionResponse(
            available=False,
            reachable=False,
            contract=contract,
            latency_ms=0,
            error_code="COZE_DISABLED",
            error_type="COZE_DISABLED",
            status="disabled",
            message="Coze crawling is disabled",
            checked_at=checked_at,
        )
    provider = CozeCrawlProvider(
        api_token=settings.coze_api_token.get_secret_value() if settings.coze_api_token else None,
        legacy_api_url=settings.coze_legacy_api_url,
        batch_api_url=settings.coze_batch_api_url,
        default_contract=settings.coze_default_contract,
        timeout_seconds=settings.coze_timeout_seconds,
        max_retries=settings.coze_max_retries,
    )
    result = await provider.test_connection(contract=contract, source_url=source.homepage_url)
    status_text = "available" if result.available else "unavailable"
    await service.record_coze_test(source_id, status=status_text, error_code=result.error_code)
    return CozeConnectionResponse(
        available=result.available,
        reachable=result.available,
        contract=result.contract,
        status_code=result.status_code,
        latency_ms=result.latency_ms,
        error_code=result.error_code,
        error_type=result.error_code,
        status=status_text,
        message=None if result.available else "Coze connectivity test failed",
        checked_at=checked_at,
    )
