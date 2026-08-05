from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from ipaddress import IPv4Network, IPv6Network, ip_address, ip_network
from typing import Any, Protocol, cast

from fastapi import Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
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


class RateLimitBackendUnavailable(RuntimeError):
    """Raised when the shared limiter cannot reach Redis."""


class RateLimiter(Protocol):
    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision: ...

    async def close(self) -> None: ...


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

    async def close(self) -> None:
        return None


class RedisFixedWindowRateLimiter:
    """Shared fixed-window limiter backed by Redis atomic counters.

    The window is part of the key, so expired counters never need an in-process
    cleanup pass. Redis is deliberately fail-closed: a production instance must
    not silently fall back to a per-process limiter when the shared dependency is
    unavailable.
    """

    def __init__(
        self,
        redis_url: str,
        *,
        key_prefix: str = "odirag:ratelimit",
        client: Redis | None = None,
        clock: Callable[[], float] = time.time,
        timeout_seconds: float = 2.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.redis_url = redis_url
        self.key_prefix = key_prefix.rstrip(":")
        self._client = client or Redis.from_url(
            redis_url,
            decode_responses=True,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )
        self._owns_client = client is None
        self._clock = clock

    async def check(self, key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
        now = self._clock()
        window = int(now // window_seconds)
        reset_after = max(1, math.ceil(((window + 1) * window_seconds) - now))
        redis_key = f"{self.key_prefix}:{window_seconds}:{window}:{key}"
        try:
            raw_result = self._client.eval(
                _FIXED_WINDOW_SCRIPT,
                1,
                redis_key,
                str(reset_after),
            )
            count_raw, ttl_raw = await cast(Awaitable[Any], raw_result)
            count = int(count_raw)
            ttl = int(ttl_raw)
        except Exception as exc:
            raise RateLimitBackendUnavailable("Redis rate limiter is unavailable") from exc
        if ttl > 0:
            reset_after = ttl
        if count > limit:
            return RateLimitDecision(False, limit, 0, reset_after)
        return RateLimitDecision(True, limit, max(0, limit - count), reset_after)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()


_FIXED_WINDOW_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return {count, redis.call('TTL', KEYS[1])}
"""


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        limiter: RateLimiter,
    ) -> None:
        super().__init__(app)
        self.settings = settings
        self.limiter = limiter
        self.trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...] = tuple(
            ip_network(value, strict=False) for value in settings.trusted_proxy_ips
        )

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if not self.settings.rate_limit_enabled or request.method == "OPTIONS":
            return await call_next(request)

        profile, limit = _profile(request, self.settings)
        key = f"{profile}:{_identity(request, self.trusted_proxy_networks)}"
        try:
            decision = await self.limiter.check(
                key,
                limit=limit,
                window_seconds=self.settings.rate_limit_window_seconds,
            )
        except RateLimitBackendUnavailable:
            request_id = getattr(request.state, "request_id", None)
            payload = ErrorResponse(
                error=ErrorDetail(
                    code="RATE_LIMIT_BACKEND_UNAVAILABLE",
                    message="Rate limiting dependency is unavailable",
                    request_id=str(request_id) if request_id is not None else None,
                )
            )
            return JSONResponse(
                status_code=503,
                content=jsonable_encoder(payload, exclude_none=True),
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


def _identity(
    request: Request,
    trusted_proxy_networks: tuple[IPv4Network | IPv6Network, ...],
) -> str:
    """Return an IP-only limiter identity without parsing unverified credentials."""

    client_host = request.client.host if request.client is not None else "unknown"
    try:
        peer = ip_address(client_host)
    except ValueError:
        return f"ip:{client_host}"

    if not any(peer in network for network in trusted_proxy_networks):
        return f"ip:{peer.compressed}"

    # Nginx overwrites this header with its direct peer address. Accept exactly
    # one value so a client-provided forwarded chain can never choose a bucket.
    forwarded_for = request.headers.get("x-forwarded-for", "")
    values = [item.strip() for item in forwarded_for.split(",") if item.strip()]
    if len(values) != 1:
        return f"ip:{peer.compressed}"
    try:
        return f"ip:{ip_address(values[0]).compressed}"
    except ValueError:
        return f"ip:{peer.compressed}"
