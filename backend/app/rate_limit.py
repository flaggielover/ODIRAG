from __future__ import annotations

import asyncio
import hashlib
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.config import Settings
from app.errors import ErrorDetail, ErrorResponse


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class InMemoryFixedWindowRateLimiter:
    """Process-local fixed-window limiter with atomic updates per application instance."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._entries: dict[str, tuple[int, int]] = {}
        self._lock = asyncio.Lock()

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        window = int(now // window_seconds)
        reset_after = max(1, math.ceil(((window + 1) * window_seconds) - now))
        async with self._lock:
            stored_window, count = self._entries.get(key, (window, 0))
            if stored_window != window:
                count = 0
            if count >= limit:
                return RateLimitDecision(False, limit, 0, reset_after)
            count += 1
            self._entries[key] = (window, count)
            if len(self._entries) > 10_000:
                self._entries = {
                    entry_key: entry
                    for entry_key, entry in self._entries.items()
                    if entry[0] == window
                }
            return RateLimitDecision(True, limit, max(0, limit - count), reset_after)


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        limiter: InMemoryFixedWindowRateLimiter,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.limiter = limiter

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.settings.rate_limit_enabled or request.method == "OPTIONS":
            return await call_next(request)

        profile, limit = _profile(request, self.settings)
        key = f"{profile}:{_identity(request, profile)}"
        decision = await self.limiter.check(
            key,
            limit=limit,
            window_seconds=self.settings.rate_limit_window_seconds,
        )
        headers = {
            "X-RateLimit-Limit": str(decision.limit),
            "X-RateLimit-Remaining": str(decision.remaining),
            "X-RateLimit-Reset": str(decision.reset_after_seconds),
        }
        if not decision.allowed:
            headers["Retry-After"] = str(decision.reset_after_seconds)
            request_id = getattr(request.state, "request_id", None)
            payload = ErrorResponse(
                error=ErrorDetail(
                    code="RATE_LIMITED",
                    message="Too many requests",
                    details={"profile": profile},
                    request_id=str(request_id) if request_id is not None else None,
                )
            )
            return JSONResponse(
                status_code=429,
                content=jsonable_encoder(payload, exclude_none=True),
                headers=headers,
            )

        response = await call_next(request)
        response.headers.update(headers)
        return response


def _profile(request: Request, settings: Settings) -> tuple[str, int]:
    path = request.url.path
    method = request.method
    auth_paths = {
        f"{settings.api_prefix}/auth/login",
        f"{settings.api_prefix}/auth/refresh",
    }
    if method == "POST" and path in auth_paths:
        return "auth", settings.rate_limit_auth_requests

    expensive_prefixes = (
        f"{settings.api_prefix}/chat",
        f"{settings.api_prefix}/search",
        f"{settings.api_prefix}/evaluations",
        f"{settings.api_prefix}/experiments",
        f"{settings.api_prefix}/source-discovery",
    )
    expensive_suffixes = ("/test", "/reindex", "/reparse", "/run")
    if method not in {"GET", "HEAD"} and (
        path.startswith(expensive_prefixes) or path.endswith(expensive_suffixes)
    ):
        return "expensive", settings.rate_limit_expensive_requests
    return "default", settings.rate_limit_default_requests


def _identity(request: Request, profile: str) -> str:
    client_host = request.client.host if request.client is not None else "unknown"
    authorization = request.headers.get("authorization", "")
    if profile != "auth" and authorization.lower().startswith("bearer "):
        digest = hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:24]
        return f"token:{digest}"
    return f"ip:{client_host}"
