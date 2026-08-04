from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings
from app.database.base import Base


class DatabaseManager:
    """Owns SQLAlchemy engines and session factories for one application instance."""

    def __init__(self, settings: Settings) -> None:
        engine_options: dict[str, object] = {
            "echo": settings.database_echo,
            "pool_pre_ping": True,
        }
        if not settings.database_url.startswith("sqlite"):
            engine_options.update(
                pool_size=settings.database_pool_size,
                max_overflow=settings.database_max_overflow,
            )
        self.async_engine: AsyncEngine = create_async_engine(
            settings.database_url,
            **engine_options,
        )
        self.session_factory = async_sessionmaker(
            bind=self.async_engine,
            expire_on_commit=False,
            class_=AsyncSession,
            autoflush=False,
        )
        self._sync_database_url = settings.sync_database_url
        self._database_echo = settings.database_echo
        self._sync_engine: Engine | None = None

    @property
    def sync_engine(self) -> Engine:
        if self._sync_engine is None:
            options: dict[str, object] = {
                "echo": self._database_echo,
                "pool_pre_ping": True,
            }
            self._sync_engine = create_engine(self._sync_database_url, **options)
        return self._sync_engine

    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as db_session:
            try:
                yield db_session
            except Exception:
                await db_session.rollback()
                raise

    async def create_schema(self) -> None:
        async with self.async_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def dispose(self) -> None:
        await self.async_engine.dispose()
        if self._sync_engine is not None:
            self._sync_engine.dispose()
