from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import selectinload

from app.core.repository import TenantScopedRepository
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.ratings.constants import MAX_RATING, MIN_RATING
from app.ratings.models import Review, ReviewRequest, ReviewRequestStatus


class ReviewRepository(TenantScopedRepository[Review]):
    model = Review

    def base_select(self) -> Select[tuple[Review]]:
        return super().base_select().options(selectinload(Review.images))

    def product_select(
        self, product_id: UUID, *, approved_only: bool = True
    ) -> Select[tuple[Review]]:
        stmt = self.base_select().where(Review.product_id == product_id)
        if approved_only:
            stmt = stmt.where(Review.is_approved.is_(True))
        return stmt.order_by(Review.created_at.desc())

    def moderation_select(self, *, is_approved: bool | None = None) -> Select[tuple[Review]]:
        stmt = self.base_select()
        if is_approved is not None:
            stmt = stmt.where(Review.is_approved.is_(is_approved))
        return stmt.order_by(Review.created_at.desc())

    async def get_by_author(self, product_id: UUID, user_id: UUID) -> Review | None:
        return await self.find_one(
            Review.product_id == product_id, Review.user_id == user_id
        )

    async def delivered_order_id(self, customer_id: UUID, product_id: UUID) -> UUID | None:
        """The customer's most recent delivered order containing the product, if any."""
        stmt = (
            select(Order.id)
            .join(
                OrderItem,
                and_(
                    OrderItem.tenant_id == Order.tenant_id,
                    OrderItem.order_id == Order.id,
                ),
            )
            .where(
                Order.tenant_id == self.tenant_id,
                Order.customer_id == customer_id,
                Order.status == OrderStatus.DELIVERED.value,
                OrderItem.product_id == product_id,
            )
            .order_by(Order.created_at.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def rating_counts(
        self, product_id: UUID, *, approved_only: bool = True
    ) -> dict[int, int]:
        """How many reviews sit at each star, zeroes included."""
        stmt = (
            select(Review.rating, func.count(Review.id))
            .where(
                Review.tenant_id == self.tenant_id,
                Review.product_id == product_id,
            )
            .group_by(Review.rating)
        )
        if approved_only:
            stmt = stmt.where(Review.is_approved.is_(True))
        result = await self.session.execute(stmt)

        counts = {star: 0 for star in range(MIN_RATING, MAX_RATING + 1)}
        counts.update({rating: count for rating, count in result.all()})
        return counts


class ReviewRequestRepository(TenantScopedRepository[ReviewRequest]):
    model = ReviewRequest

    async def for_order(self, order_id: UUID) -> ReviewRequest | None:
        return await self.find_one(ReviewRequest.order_id == order_id)

    def list_select(self, *, status: ReviewRequestStatus | None = None) -> Select:
        stmt = self.base_select()
        if status is not None:
            stmt = stmt.where(ReviewRequest.status == status.value)
        return stmt.order_by(ReviewRequest.send_after.desc())
