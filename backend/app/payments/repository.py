from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, select

from app.core.repository import TenantScopedRepository
from app.payments.constants import PaymentStatus
from app.payments.models import Payment


class PaymentRepository(TenantScopedRepository[Payment]):
    model = Payment

    def list_select(
        self,
        *,
        order_id: UUID | None = None,
        status: PaymentStatus | None = None,
    ) -> Select[tuple[Payment]]:
        stmt = self.base_select()

        if order_id is not None:
            stmt = stmt.where(Payment.order_id == order_id)

        if status is not None:
            stmt = stmt.where(Payment.status == status.value)

        return stmt.order_by(Payment.created_at.desc())

    async def get_razorpay_payment_for_update(
        self, order_id: UUID, razorpay_order_id: str | None = None
    ) -> Payment | None:
        stmt = self.base_select().where(
            Payment.order_id == order_id,
            Payment.provider == "RAZORPAY",
        )
        if razorpay_order_id is not None:
            stmt = stmt.where(Payment.razorpay_order_id == razorpay_order_id)
        return await self.session.scalar(
            stmt.with_for_update().execution_options(populate_existing=True)
        )

    async def get_by_razorpay_order_id(self, razorpay_order_id: str) -> Payment | None:
        return await self.find_one(Payment.razorpay_order_id == razorpay_order_id)

    async def razorpay_payment_id_exists(self, razorpay_payment_id: str) -> bool:
        # Gateway payment ids are globally unique; this check deliberately
        # does not reveal which tenant, if any, already recorded the id.
        existing = await self.session.scalar(
            select(Payment.id).where(Payment.razorpay_payment_id == razorpay_payment_id)
        )
        return existing is not None
