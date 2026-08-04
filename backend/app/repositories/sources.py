from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Source, SourceColumn


class SourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _with_columns(statement: Select[tuple[Source]]) -> Select[tuple[Source]]:
        return statement.options(selectinload(Source.columns))

    async def list_all(self, *, enabled: bool | None = None) -> list[Source]:
        statement = self._with_columns(select(Source)).order_by(Source.priority.desc(), Source.id)
        if enabled is not None:
            statement = statement.where(Source.enabled.is_(enabled))
        result = await self._session.execute(statement)
        return list(result.scalars().unique())

    async def get(self, source_id: int) -> Source | None:
        result = await self._session.execute(
            self._with_columns(select(Source).where(Source.id == source_id))
        )
        return result.scalar_one_or_none()

    async def get_by_key(self, source_key: str) -> Source | None:
        result = await self._session.execute(
            self._with_columns(select(Source).where(Source.source_key == source_key))
        )
        return result.scalar_one_or_none()

    async def create(self, source: Source, columns: list[SourceColumn]) -> Source:
        source.columns.extend(columns)
        self._session.add(source)
        await self._session.commit()
        return await self._required(source.id)

    async def save(self, source: Source) -> Source:
        await self._session.commit()
        return await self._required(source.id)

    async def delete(self, source: Source) -> None:
        await self._session.delete(source)
        await self._session.commit()

    async def _required(self, source_id: int) -> Source:
        source = await self.get(source_id)
        if source is None:
            raise RuntimeError("source disappeared after persistence")
        return source
