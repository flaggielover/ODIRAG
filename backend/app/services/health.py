from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import httpx
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.schemas.system import DependencyHealth, HealthResponse


class HealthService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    async def check(self) -> HealthResponse:
        checks: dict[str, Awaitable[DependencyHealth]] = {
            "database": self._timed_check(self._check_database),
            "redis": self._timed_check(self._check_redis),
        }
        if self._settings.health_check_qdrant:
            checks["qdrant"] = self._timed_check(self._check_qdrant)
        else:
            checks["qdrant"] = self._disabled()

        names = list(checks)
        results = await asyncio.gather(*(checks[name] for name in names))
        dependencies = dict(zip(names, results, strict=True))
        status = (
            "healthy"
            if all(dependency.status in {"healthy", "disabled"} for dependency in results)
            else "degraded"
        )
        return HealthResponse(
            status=status,
            service=self._settings.app_name,
            environment=self._settings.environment,
            checked_at=datetime.now(UTC),
            dependencies=dependencies,
        )

    async def _timed_check(self, operation: Callable[[], Awaitable[None]]) -> DependencyHealth:
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._settings.dependency_timeout_seconds):
                await operation()
        except Exception as exc:
            return DependencyHealth(
                status="unavailable",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                detail=self._safe_error_detail(exc),
            )
        return DependencyHealth(
            status="healthy",
            latency_ms=round((time.perf_counter() - started) * 1000, 2),
        )

    async def _check_database(self) -> None:
        await self._session.execute(text("SELECT 1"))

    async def _check_redis(self) -> None:
        client = Redis.from_url(
            self._settings.redis_url,
            socket_connect_timeout=self._settings.dependency_timeout_seconds,
            socket_timeout=self._settings.dependency_timeout_seconds,
        )
        try:
            await client.ping()
        finally:
            await client.aclose()

    async def _check_qdrant(self) -> None:
        async with httpx.AsyncClient(timeout=self._settings.dependency_timeout_seconds) as client:
            response = await client.get(f"{self._settings.qdrant_url.rstrip('/')}/healthz")
            response.raise_for_status()

    async def _disabled(self) -> DependencyHealth:
        return DependencyHealth(status="disabled", detail="Health check disabled by configuration")

    @staticmethod
    def _safe_error_detail(exc: Exception) -> str:
        if isinstance(exc, TimeoutError):
            return "timed out"
        return exc.__class__.__name__
