"""Admin view of customers: lifetime totals, tags and notes."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.models import Address
from app.auth.constants import UserRole
from app.core.error_codes import UserErrorCode
from app.core.exceptions import NotFoundError
from app.core.money import money
from app.customers.models import CustomerNote
from app.customers.schemas import CustomerQuery
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.users.models import User

CUSTOMER_NOT_FOUND = "Customer not found"


def _order_stats(tenant_id: UUID):
    """Per-customer order totals. Cancelled orders do not count as spending."""
    live = Order.status != OrderStatus.CANCELLED.value
    return (
        select(
            Order.customer_id.label("customer_id"),
            func.count(case((live, Order.id))).label("total_orders"),
            func.coalesce(func.sum(case((live, Order.total_amount))), 0).label("total_spent"),
            func.max(Order.created_at).label("last_order_at"),
            func.min(Order.created_at).label("first_order_at"),
            func.count(case((Order.status == OrderStatus.CANCELLED.value, Order.id))).label(
                "cancelled_orders"
            ),
            func.count(case((Order.status == OrderStatus.RETURNED.value, Order.id))).label(
                "returned_orders"
            ),
        )
        .where(Order.tenant_id == tenant_id)
        .group_by(Order.customer_id)
        .subquery()
    )


class CustomerService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _select(self) -> tuple[Select, object]:
        stats = _order_stats(self.tenant_id)
        stmt = (
            select(User, stats)
            .outerjoin(stats, stats.c.customer_id == User.id)
            .where(User.tenant_id == self.tenant_id, User.role == UserRole.CUSTOMER.value)
        )
        return stmt, stats

    async def list(self, query: CustomerQuery):
        stmt, stats = self._select()
        if query.search:
            term = f"%{query.search.strip()}%"
            stmt = stmt.where(
                User.name.ilike(term) | User.email.ilike(term) | User.phone.ilike(term)
            )
        if query.tag:
            stmt = stmt.where(User.tags.contains([query.tag.strip()]))
        if query.status:
            stmt = stmt.where(User.status == query.status)
        if query.blocked is not None:
            stmt = stmt.where(
                User.order_blocked_at.isnot(None)
                if query.blocked
                else User.order_blocked_at.is_(None)
            )

        order = {
            "newest": (desc(User.created_at),),
            "total_spent": (desc(func.coalesce(stats.c.total_spent, 0)),),
            "orders": (desc(func.coalesce(stats.c.total_orders, 0)),),
            "last_order": (stats.c.last_order_at.desc().nulls_last(),),
        }[query.sort]

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await self.session.execute(
                stmt.order_by(*order, User.id).offset(query.offset).limit(query.limit)
            )
        ).all()
        return [self._row(row) for row in rows], int(total or 0)

    async def get(self, customer_id: UUID) -> dict:
        stmt, _stats = self._select()
        row = (await self.session.execute(stmt.where(User.id == customer_id))).first()
        if row is None:
            raise NotFoundError(CUSTOMER_NOT_FOUND, error_code=UserErrorCode.NOT_FOUND)
        detail = self._row(row)
        detail["first_order_at"] = row.first_order_at
        detail["cancelled_orders"] = row.cancelled_orders or 0
        detail["returned_orders"] = row.returned_orders or 0
        detail["is_returning"] = detail["total_orders"] > 1
        detail["addresses"] = list(
            (
                await self.session.scalars(
                    select(Address)
                    .where(Address.tenant_id == self.tenant_id, Address.customer_id == customer_id)
                    .order_by(desc(Address.is_default), Address.created_at)
                )
            ).all()
        )
        detail["notes"] = await self.notes(customer_id)
        return detail

    @staticmethod
    def _row(row) -> dict:
        user: User = row[0]
        return {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "status": user.status,
            "is_verified": user.is_verified,
            "tags": user.tags or [],
            "order_blocked": user.order_blocked_at is not None,
            "order_blocked_at": user.order_blocked_at,
            "order_block_reason": user.order_block_reason,
            "total_orders": row.total_orders or 0,
            "total_spent": money(Decimal(row.total_spent or 0)),
            "last_order_at": row.last_order_at,
            "created_at": user.created_at,
        }

    async def require(self, customer_id: UUID) -> User:
        user = await self.session.scalar(
            select(User).where(
                and_(
                    User.tenant_id == self.tenant_id,
                    User.id == customer_id,
                    User.role == UserRole.CUSTOMER.value,
                )
            )
        )
        if user is None:
            raise NotFoundError(CUSTOMER_NOT_FOUND, error_code=UserErrorCode.NOT_FOUND)
        return user

    async def set_tags(self, customer_id: UUID, tags: list[str]) -> User:
        user = await self.require(customer_id)
        user.tags = tags
        await self.session.flush()
        return user

    async def set_order_block(self, customer_id: UUID, blocked: bool, reason: str | None) -> User:
        """Stop (or allow again) new orders from this customer. Existing orders stay as they are."""
        user = await self.require(customer_id)
        if blocked:
            user.order_blocked_at = user.order_blocked_at or datetime.now(timezone.utc)
            user.order_block_reason = reason
        else:
            user.order_blocked_at = None
            user.order_block_reason = None
        await self.session.flush()
        return user

    async def all_tags(self) -> list[str]:
        rows = await self.session.scalars(
            select(func.jsonb_array_elements_text(User.tags)).where(
                User.tenant_id == self.tenant_id,
                User.role == UserRole.CUSTOMER.value,
                User.tags.isnot(None),
            )
        )
        return sorted(set(rows.all()), key=str.lower)

    async def notes(self, customer_id: UUID) -> list[CustomerNote]:
        rows = await self.session.scalars(
            select(CustomerNote)
            .where(
                CustomerNote.tenant_id == self.tenant_id,
                CustomerNote.customer_id == customer_id,
            )
            .order_by(CustomerNote.created_at.desc())
        )
        return list(rows.all())

    async def add_note(self, customer_id: UUID, author: User, body: str) -> CustomerNote:
        await self.require(customer_id)
        note = CustomerNote(
            tenant_id=self.tenant_id,
            customer_id=customer_id,
            author_id=author.id,
            author_name=author.name or author.email or author.phone,
            body=body,
        )
        self.session.add(note)
        await self.session.flush()
        return note

    async def delete_note(self, customer_id: UUID, note_id: UUID) -> None:
        note = await self.session.scalar(
            select(CustomerNote).where(
                CustomerNote.tenant_id == self.tenant_id,
                CustomerNote.customer_id == customer_id,
                CustomerNote.id == note_id,
            )
        )
        if note is None:
            raise NotFoundError("Note not found")
        await self.session.delete(note)
        await self.session.flush()
