from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import conflict_on_integrity_error
from app.core.exceptions import ConflictError, NotFoundError
from app.returns.models import ReturnReason

REASON_NOT_FOUND = "Return reason not found"
DUPLICATE = "A return reason with this label already exists"


class ReturnReasonService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def list(self, *, active_only: bool = False) -> list[ReturnReason]:
        stmt = select(ReturnReason).where(ReturnReason.tenant_id == self.tenant_id)
        if active_only:
            stmt = stmt.where(ReturnReason.is_active.is_(True))
        rows = await self.session.scalars(stmt.order_by(ReturnReason.position, ReturnReason.label))
        return list(rows.all())

    async def get(self, reason_id: UUID) -> ReturnReason:
        reason = await self.session.scalar(
            select(ReturnReason).where(
                ReturnReason.tenant_id == self.tenant_id, ReturnReason.id == reason_id
            )
        )
        if reason is None:
            raise NotFoundError(REASON_NOT_FOUND)
        return reason

    async def require_active(self, reason_id: UUID) -> ReturnReason:
        reason = await self.get(reason_id)
        if not reason.is_active:
            raise ConflictError("This return reason is switched off")
        return reason

    async def create(self, label: str, is_active: bool) -> ReturnReason:
        top = await self.session.scalar(
            select(func.max(ReturnReason.position)).where(ReturnReason.tenant_id == self.tenant_id)
        )
        reason = ReturnReason(
            tenant_id=self.tenant_id,
            label=label,
            is_active=is_active,
            position=0 if top is None else top + 1,
        )
        self.session.add(reason)
        await self._commit()
        await self.session.refresh(reason)
        return reason

    async def update(self, reason_id: UUID, changes: dict) -> ReturnReason:
        reason = await self.get(reason_id)
        for field, value in changes.items():
            setattr(reason, field, value)
        await self._commit()
        await self.session.refresh(reason)
        return reason

    async def _commit(self) -> None:
        async with conflict_on_integrity_error(self.session, DUPLICATE):
            await self.session.commit()
