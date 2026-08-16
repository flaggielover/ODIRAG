from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.routes import health, prometheus
from app.config import Settings, get_settings
from app.database.session import DatabaseManager
from app.errors import register_error_handlers
from app.logging import RequestContextMiddleware, configure_logging
from app.metrics import MetricsMiddleware, MetricsRegistry
from app.rate_limit import (
    InMemoryFixedWindowRateLimiter,
    RateLimiter,
    RateLimitMiddleware,
    RedisFixedWindowRateLimiter,
)
from app.repositories.users import UserRepository
from app.runtime import build_application_runtime
from app.services.auth import AuthService


def create_app(
    settings: Settings | None = None,
    *,
    database: DatabaseManager | None = None,
) -> FastAPI:
    app_settings = settings or get_settings()
    configure_logging(app_settings)
    database_manager = database or DatabaseManager(app_settings)
    metrics_registry = MetricsRegistry()
    rate_limiter: RateLimiter
    if app_settings.rate_limit_backend == "redis" and app_settings.environment != "test":
        rate_limiter = RedisFixedWindowRateLimiter(
            app_settings.redis_url,
            timeout_seconds=app_settings.dependency_timeout_seconds,
        )
    else:
        rate_limiter = InMemoryFixedWindowRateLimiter()
    application_runtime = build_application_runtime(
        app_settings,
        observability_recorder=metrics_registry,
    )
    metrics_registry.attach_database_engine(database_manager.async_engine.sync_engine)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        logger = structlog.get_logger(__name__)
        try:
            if app_settings.auto_create_schema:
                await database_manager.create_schema()
            try:
                async with database_manager.session_factory() as session:
                    await AuthService(UserRepository(session), app_settings).bootstrap_admin()
            except Exception as exc:
                logger.warning(
                    "admin_bootstrap_unavailable",
                    error_type=exc.__class__.__name__,
                )
            logger.info(
                "application_started",
                environment=app_settings.environment,
                database_driver=database_manager.async_engine.url.drivername,
            )
            yield
        finally:
            await application_runtime.close()
            try:
                await rate_limiter.close()
            finally:
                await database_manager.dispose()
            logger.info("application_stopped")

    app = FastAPI(
        title=app_settings.app_name,
        version="0.1.0",
        debug=app_settings.debug,
        lifespan=lifespan,
        openapi_url=f"{app_settings.api_prefix}/openapi.json",
        docs_url=f"{app_settings.api_prefix}/docs",
        redoc_url=f"{app_settings.api_prefix}/redoc",
    )
    app.state.settings = app_settings
    app.state.database = database_manager
    app.state.metrics = metrics_registry
    app.state.rate_limiter = rate_limiter
    app.state.runtime = application_runtime

    app.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.add_middleware(
        RateLimitMiddleware,
        settings=app_settings,
        limiter=rate_limiter,
    )
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        MetricsMiddleware,
        registry=metrics_registry,
        api_prefix=app_settings.api_prefix,
    )
    register_error_handlers(app)
    # Root probes are deliberately outside the versioned API prefix so
    # orchestrators can check process/dependency health without API auth.
    app.include_router(health.router)
    # Prometheus is an internal backend endpoint.  It is intentionally not
    # added to the public Nginx configuration.
    app.include_router(prometheus.router)
    app.include_router(api_router, prefix=app_settings.api_prefix)
    return app


app = create_app()
