from __future__ import annotations

import time
from datetime import UTC, datetime

import httpx
from sqlalchemy.exc import IntegrityError

from app.crawler.fetcher import HttpFetcher
from app.crawler.urls import HostResolver
from app.errors import ConflictError, NotFoundError
from app.models import Source, SourceColumn
from app.repositories.sources import SourceRepository
from app.schemas.source import SourceCreate, SourceTestResponse, SourceUpdate


class SourceService:
    def __init__(
        self,
        repository: SourceRepository,
        *,
        timeout_seconds: float = 10.0,
        max_bytes: int = 256 * 1024,
        max_redirects: int = 5,
        client: httpx.AsyncClient | None = None,
        resolver: HostResolver | None = None,
    ) -> None:
        self._repository = repository
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._max_redirects = max_redirects
        self._client = client
        self._resolver = resolver

    async def list(self, *, enabled: bool | None = None) -> list[Source]:
        return await self._repository.list_all(enabled=enabled)

    async def get(self, source_id: int) -> Source:
        source = await self._repository.get(source_id)
        if source is None:
            raise NotFoundError("Source", source_id)
        return source

    async def create(self, payload: SourceCreate) -> Source:
        source_data = payload.model_dump(exclude={"columns"}, mode="json")
        source_data["homepage_url"] = str(payload.homepage_url)
        source = Source(**source_data)
        columns = [
            SourceColumn(
                **column.model_dump(exclude={"column_url"}, mode="json"),
                column_url=str(column.column_url),
            )
            for column in payload.columns
        ]
        try:
            return await self._repository.create(source, columns)
        except IntegrityError as exc:
            raise ConflictError("Source key or column key already exists") from exc

    async def update(self, source_id: int, payload: SourceUpdate) -> Source:
        source = await self.get(source_id)
        changes = payload.model_dump(exclude_unset=True, mode="json")
        if payload.homepage_url is not None:
            changes["homepage_url"] = str(payload.homepage_url)
        if payload.domain is not None:
            changes["domain"] = payload.domain.strip().lower().rstrip(".")
        for field_name, value in changes.items():
            setattr(source, field_name, value)
        return await self._repository.save(source)

    async def delete(self, source_id: int) -> None:
        await self._repository.delete(await self.get(source_id))

    async def record_coze_test(
        self, source_id: int, *, status: str, error_code: str | None
    ) -> Source:
        source = await self.get(source_id)
        source.last_coze_test_at = datetime.now(UTC)
        source.last_coze_status = status
        source.last_coze_error = error_code
        return await self._repository.save(source)

    async def test(self, source_id: int) -> SourceTestResponse:
        source = await self.get(source_id)
        fetcher = HttpFetcher(
            timeout_seconds=self._timeout_seconds,
            max_bytes=self._max_bytes,
            max_redirects=self._max_redirects,
            user_agent="ODIRAG/0.1 source-health-check",
            client=self._client,
            resolver=self._resolver,
        )
        started = time.perf_counter()
        try:
            response = await fetcher.fetch(source.homepage_url)
            latency = round((time.perf_counter() - started) * 1000, 2)
            return SourceTestResponse(
                reachable=True,
                status_code=response.status_code,
                latency_ms=latency,
                final_url=response.url,
            )
        except httpx.HTTPStatusError as exc:
            return SourceTestResponse(
                reachable=False,
                status_code=exc.response.status_code,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                final_url=str(exc.response.url),
                error_type=exc.__class__.__name__,
            )
        except httpx.HTTPError as exc:
            return SourceTestResponse(
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=exc.__class__.__name__,
            )
        except (TimeoutError, ValueError) as exc:
            return SourceTestResponse(
                reachable=False,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=exc.__class__.__name__,
            )
