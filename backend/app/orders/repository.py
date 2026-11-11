from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from sqlalchemy import Select, and_, exists, or_, select

from app.core.repository import TenantScopedRepository
from app.orders.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.orders.models import Order, OrderItem
from app.users.models import User


def _escape_like(term: str) -> str:
    """Neutralise LIKE wildcards so a search term cannot widen its own match."""
    return term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


class OrderRepository(TenantScopedRepository[Order]):
    model = Order

    async def get_by_idempotency_key(self, customer_id: UUID, key: str) -> Order | None:
        return await self.find_one(
            Order.customer_id == customer_id, Order.idempotency_key == key
        )

    async def lock(self, order_id: UUID) -> Order | None:
        """Re-read an order fresh from the database with a row lock, so two
        status or payment changes to it run one after the other."""
        return await self.session.scalar(
            self.base_select()
            .where(Order.id == order_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def lock_for_customer(self, customer_id: UUID, order_id: UUID) -> Order | None:
        """Lock only an order owned by this customer in the current tenant."""
        return await self.session.scalar(
            self.base_select()
            .where(Order.id == order_id, Order.customer_id == customer_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

    async def get_for_customer_for_update(
        self, customer_id: UUID, order_id: UUID
    ) -> Order | None:
        """Compatibility name used by the Razorpay lock protocol."""
        return await self.lock_for_customer(customer_id, order_id)

    def list_select(
        self,
        *,
        customer_id: UUID | None = None,
        order_number: str | None = None,
        status: OrderStatus | None = None,
        payment_status: PaymentStatus | None = None,
        search: str | None = None,
        payment_method: PaymentMethod | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> Select[tuple[Order]]:
        stmt = self.base_select()

        if search:
            stmt = stmt.where(self._matches(search.strip()))

        if payment_method:
            stmt = stmt.where(Order.payment_method == payment_method.value)

        if start_date:
            stmt = stmt.where(
                Order.created_at >= datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            )
        if end_date:
            stmt = stmt.where(
                Order.created_at
                < datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=timezone.utc)
            )

        if customer_id is not None:
            stmt = stmt.where(Order.customer_id == customer_id)

        if order_number:
            pattern = f"%{_escape_like(order_number.strip())}%"
            stmt = stmt.where(Order.order_number.ilike(pattern, escape="\\"))

        if status is not None:
            stmt = stmt.where(Order.status == status.value)

        if payment_status is not None:
            stmt = stmt.where(Order.payment_status == payment_status.value)

        return stmt.order_by(Order.created_at.desc())

    def _matches(self, term: str):
        """Order number, customer name/phone/email, delivery name/phone, product or SKU."""
        pattern = f"%{_escape_like(term)}%"
        customer = select(User.id).where(
            User.tenant_id == self.tenant_id,
            User.id == Order.customer_id,
            or_(
                User.name.ilike(pattern, escape="\\"),
                User.phone.ilike(pattern, escape="\\"),
                User.email.ilike(pattern, escape="\\"),
            ),
        )
        product = select(OrderItem.id).where(
            and_(
                OrderItem.tenant_id == Order.tenant_id,
                OrderItem.order_id == Order.id,
                or_(
                    OrderItem.product_name.ilike(pattern, escape="\\"),
                    OrderItem.sku.ilike(pattern, escape="\\"),
                ),
            )
        )
        return or_(
            Order.order_number.ilike(pattern, escape="\\"),
            Order.delivery_name.ilike(pattern, escape="\\"),
            Order.delivery_phone.ilike(pattern, escape="\\"),
            Order.contact_email.ilike(pattern, escape="\\"),
            exists(customer),
            exists(product),
        )

    async def get_by_number(self, order_number: str) -> Order | None:
        return await self.find_one(Order.order_number == order_number)

    async def get_for_customer(self, customer_id: UUID, order_id: UUID) -> Order | None:
        """Fetch an order scoped to the customer as well as the tenant."""
        return await self.find_one(
            Order.id == order_id, Order.customer_id == customer_id
        )
