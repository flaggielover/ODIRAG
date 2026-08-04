from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, QueryTrace


class ChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_approved_documents(self, filters: dict[str, Any]) -> int:
        statement = (
            select(func.count()).select_from(Document).where(Document.final_status == "approved")
        )
        statement = _apply_document_filters(statement, filters)
        value = await self.session.scalar(statement)
        return int(value or 0)

    async def add_trace(self, trace: QueryTrace) -> QueryTrace:
        self.session.add(trace)
        await self.session.flush()
        return trace

    async def get_trace(self, trace_id: str) -> QueryTrace | None:
        result = await self.session.execute(
            select(QueryTrace).where(QueryTrace.trace_id == trace_id)
        )
        return result.scalar_one_or_none()

    async def list_traces(
        self,
        *,
        limit: int = 100,
        query_type: str | None = None,
        refusal: bool | None = None,
    ) -> list[QueryTrace]:
        statement = select(QueryTrace)
        if query_type is not None:
            statement = statement.where(QueryTrace.query_type == query_type)
        if refusal is not None:
            statement = statement.where(QueryTrace.refusal.is_(refusal))
        result = await self.session.execute(
            statement.order_by(QueryTrace.created_at.desc(), QueryTrace.id.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def commit(self) -> None:
        await self.session.commit()


def _apply_document_filters(
    statement: Select[tuple[int]], filters: dict[str, Any]
) -> Select[tuple[int]]:
    for key, value in filters.items():
        if key == "document_id":
            statement = statement.where(Document.document_id == str(value))
        elif key == "source_id":
            statement = statement.where(Document.source_id == int(value))
        elif key == "region":
            statement = statement.where(Document.region == str(value))
        elif key == "city":
            statement = statement.where(Document.city == str(value))
        elif key == "document_type":
            statement = statement.where(Document.document_type == str(value))
        elif key == "issuing_authority":
            statement = statement.where(Document.issuing_authority == str(value))
        elif key == "publish_date_gte":
            statement = statement.where(Document.publish_date >= date.fromisoformat(str(value)))
        elif key == "publish_date_lte":
            statement = statement.where(Document.publish_date <= date.fromisoformat(str(value)))
        elif key == "document_version":
            statement = statement.where(Document.version == int(value))
        else:
            raise ValueError(f"unsupported structured filter: {key}")
    return statement
