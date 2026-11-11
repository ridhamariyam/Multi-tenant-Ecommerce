from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.core.pagination import PageParams
from app.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


def escape_like(term: str) -> str:
    """Neutralise LIKE wildcards so a search term cannot widen its own match."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class TenantScopedRepository(Generic[ModelT]):
    model: type[ModelT]

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def base_select(self) -> Select[tuple[ModelT]]:
        return select(self.model).where(self.model.tenant_id == self.tenant_id)

    async def find_one(self, *conditions: ColumnElement[bool]) -> ModelT | None:
        return await self.session.scalar(self.base_select().where(*conditions))

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.find_one(self.model.id == entity_id)

    async def add(self, entity: ModelT) -> ModelT:
        entity.tenant_id = self.tenant_id
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def paginate(
        self, stmt: Select[tuple[ModelT]], params: PageParams
    ) -> tuple[Sequence[ModelT], int]:
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = await self.session.scalars(stmt.offset(params.offset).limit(params.limit))
        return rows.all(), int(total or 0)

    async def delete(self, entity: ModelT) -> None:
        await self.session.delete(entity)
        await self.session.flush()
