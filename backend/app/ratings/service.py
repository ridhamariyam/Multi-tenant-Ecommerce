from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.uploads import store_image
from app.core.config import get_settings
from app.core.database import conflict_on_integrity_error
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.core.pagination import PageParams
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.ratings.constants import (
    ALREADY_REVIEWED,
    MAX_IMAGES_PER_REVIEW,
    NOT_DELIVERED,
    NOT_REVIEW_AUTHOR,
    REVIEW_NOT_FOUND,
)
from app.ratings.models import Review, ReviewImage, ReviewRequest, ReviewRequestStatus
from app.ratings.repository import ReviewRepository, ReviewRequestRepository
from app.ratings.schemas import (
    RatingSummaryRead,
    ReviewCreate,
    ReviewModerate,
    ReviewUpdate,
)
from app.users.repository import UserRepository


class ReviewService:
    """Product reviews. Only a delivered purchase earns one, and only one."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.reviews = ReviewRepository(session, tenant_id)

    async def create(self, customer_id: UUID, data: ReviewCreate) -> Review:
        order_id = await self.reviews.delivered_order_id(customer_id, data.product_id)
        if order_id is None:
            raise PermissionDeniedError(NOT_DELIVERED)

        if await self.reviews.get_by_author(data.product_id, customer_id) is not None:
            raise ConflictError(ALREADY_REVIEWED)

        review = Review(
            product_id=data.product_id,
            user_id=customer_id,
            order_id=order_id,
            rating=data.rating,
            title=data.title,
            comment=data.comment,
            is_verified_purchase=True,
            is_approved=True,
            images=[
                ReviewImage(
                    tenant_id=self.tenant_id,
                    image_url=image.image_url,
                    alt_text=image.alt_text,
                )
                for image in data.images
            ],
        )

        async with conflict_on_integrity_error(self.session, ALREADY_REVIEWED):
            await self.reviews.add(review)
            await self._close_request(order_id, customer_id)
            await self.session.commit()

        return review

    async def list_for_product(
        self, product_id: UUID, params: PageParams, *, approved_only: bool = True
    ) -> tuple[list[Review], int]:
        rows, total = await self.reviews.paginate(
            self.reviews.product_select(product_id, approved_only=approved_only),
            params,
        )
        return list(rows), total

    async def list_for_moderation(
        self, params: PageParams, *, is_approved: bool | None = None
    ) -> tuple[list[Review], int]:
        rows, total = await self.reviews.paginate(
            self.reviews.moderation_select(is_approved=is_approved), params
        )
        return list(rows), total

    async def summary(
        self, product_id: UUID, *, approved_only: bool = True
    ) -> RatingSummaryRead:
        counts = await self.reviews.rating_counts(
            product_id, approved_only=approved_only
        )

        total_reviews = sum(counts.values())
        total_score = sum(star * count for star, count in counts.items())
        average = round(total_score / total_reviews, 2) if total_reviews else 0.0

        return RatingSummaryRead(
            product_id=product_id,
            average_rating=average,
            total_reviews=total_reviews,
            rating_distribution=counts,
        )

    async def update(
        self, review_id: UUID, customer_id: UUID, data: ReviewUpdate
    ) -> Review:
        review = await self._owned_by(review_id, customer_id)

        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(review, field, value)

        await self.session.commit()
        return review

    async def moderate(self, review_id: UUID, data: ReviewModerate) -> Review:
        review = await self._get(review_id)
        review.is_approved = data.is_approved

        await self.session.commit()
        return review

    async def delete(self, review_id: UUID, customer_id: UUID) -> None:
        review = await self._owned_by(review_id, customer_id)

        await self.reviews.delete(review)
        await self.session.commit()

    async def _close_request(self, order_id: UUID | None, customer_id: UUID) -> None:
        await self.session.flush()
        await ReviewRequestService(self.session, self.tenant_id).complete_if_done(
            order_id, customer_id
        )

    async def add_uploaded_image(
        self,
        review_id: UUID,
        customer_id: UUID,
        *,
        filename: str,
        content_type: str,
        data: bytes,
        alt_text: str | None,
    ) -> Review:
        """Attach a photo the author uploads (JPEG/PNG/WebP, size-capped)."""
        review = await self._owned_by(review_id, customer_id)
        if len(review.images) >= MAX_IMAGES_PER_REVIEW:
            raise ValidationError(
                f"A review can have at most {MAX_IMAGES_PER_REVIEW} photos"
            )

        url = await store_image(self.tenant_id, content_type, data)
        review.images.append(
            ReviewImage(tenant_id=self.tenant_id, image_url=url, alt_text=alt_text)
        )
        await self.session.commit()

        return await self._get(review.id)

    async def delete_image(self, review_id: UUID, image_id: UUID, customer_id: UUID) -> Review:
        review = await self._owned_by(review_id, customer_id)
        image = next((img for img in review.images if img.id == image_id), None)
        if image is None:
            raise NotFoundError("Review image not found")
        review.images.remove(image)
        await self.session.commit()
        return await self._get(review.id)

    async def _get(self, review_id: UUID) -> Review:
        review = await self.reviews.get(review_id)
        if review is None:
            raise NotFoundError(REVIEW_NOT_FOUND)
        return review

    async def _owned_by(self, review_id: UUID, customer_id: UUID) -> Review:
        review = await self._get(review_id)
        if review.user_id != customer_id:
            raise PermissionDeniedError(NOT_REVIEW_AUTHOR)
        return review


# Automatic review requests after delivery.
#
# No email/SMS/WhatsApp provider is wired into this backend yet, so the default
# notifier is a no-op placeholder. Plug a real channel in by implementing
# `ReviewRequestNotifier` and passing it to `ReviewRequestService.dispatch_due`.


@dataclass
class ReviewRequestMessage:
    tenant_id: str
    order_number: str
    customer_name: str | None
    email: str | None
    phone: str
    products: list[str]


class ReviewRequestNotifier(Protocol):
    async def send(self, message: ReviewRequestMessage) -> None: ...


class NullReviewNotifier:
    """Placeholder until a real delivery channel is configured."""

    async def send(self, message: ReviewRequestMessage) -> None:
        pass


class ReviewRequestService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.requests = ReviewRequestRepository(session, tenant_id)

    async def schedule_for(self, order: Order) -> None:
        """Queue a request when an order is delivered. Caller commits."""
        if await self.requests.for_order(order.id) is not None:
            return
        delay = timedelta(days=get_settings().review_request_delay_days)
        await self.requests.add(
            ReviewRequest(
                order_id=order.id,
                customer_id=order.customer_id,
                status=ReviewRequestStatus.PENDING.value,
                send_after=datetime.now(timezone.utc) + delay,
            )
        )

    async def list(self, params, *, status: ReviewRequestStatus | None = None):
        rows, total = await self.requests.paginate(self.requests.list_select(status=status), params)
        return list(rows), total

    async def _unreviewed(self, order_id: UUID, customer_id: UUID) -> list[OrderItem]:
        """Products on the order the customer has not reviewed yet."""
        reviewed = select(Review.product_id).where(
            Review.tenant_id == self.tenant_id, Review.user_id == customer_id
        )
        rows = await self.session.scalars(
            select(OrderItem).where(
                OrderItem.tenant_id == self.tenant_id,
                OrderItem.order_id == order_id,
                OrderItem.product_id.notin_(reviewed),
            )
        )
        seen, items = set(), []
        for item in rows.all():
            if item.product_id not in seen:
                seen.add(item.product_id)
                items.append(item)
        return items

    async def pending_for_customer(self, customer_id: UUID) -> list[tuple[Order, OrderItem]]:
        """(order, item) for every delivered product still waiting for a review."""
        orders = await self.session.scalars(
            select(Order)
            .where(
                Order.tenant_id == self.tenant_id,
                Order.customer_id == customer_id,
                Order.status == OrderStatus.DELIVERED.value,
            )
            .order_by(Order.created_at.desc())
        )
        pending, seen = [], set()
        for order in orders.all():
            for item in await self._unreviewed(order.id, customer_id):
                if item.product_id not in seen:
                    seen.add(item.product_id)
                    pending.append((order, item))
        return pending

    async def dispatch_due(
        self,
        notifier: ReviewRequestNotifier | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        """Send every due request; requests whose products are all reviewed just close."""
        notifier = notifier or NullReviewNotifier()
        moment = now or datetime.now(timezone.utc)
        users = UserRepository(self.session)
        sent = completed = 0

        due = await self.session.scalars(
            self.requests.base_select().where(
                ReviewRequest.status == ReviewRequestStatus.PENDING.value,
                ReviewRequest.send_after <= moment,
            )
        )
        for request in due.all():
            order = await self.session.scalar(
                select(Order).where(
                    and_(Order.tenant_id == self.tenant_id, Order.id == request.order_id)
                )
            )
            items = await self._unreviewed(request.order_id, request.customer_id)
            if order is None or not items:
                request.status = ReviewRequestStatus.COMPLETED.value
                completed += 1
                continue

            customer = await users.get_by_id(tenant_id=self.tenant_id, user_id=request.customer_id)
            await notifier.send(
                ReviewRequestMessage(
                    tenant_id=str(self.tenant_id),
                    order_number=order.order_number,
                    customer_name=customer.name if customer else order.delivery_name,
                    email=order.contact_email or (customer.email if customer else None),
                    phone=order.delivery_phone,
                    products=[item.product_name for item in items],
                )
            )
            request.status = ReviewRequestStatus.SENT.value
            request.sent_at = moment
            sent += 1

        await self.session.commit()
        return {"sent": sent, "completed": completed}

    async def complete_if_done(self, order_id: UUID | None, customer_id: UUID) -> None:
        """Close the order's request once all its products are reviewed. Caller commits."""
        if order_id is None:
            return
        request = await self.requests.for_order(order_id)
        if request is None or request.status in {
            ReviewRequestStatus.COMPLETED.value,
            ReviewRequestStatus.CANCELLED.value,
        }:
            return
        if not await self._unreviewed(order_id, customer_id):
            request.status = ReviewRequestStatus.COMPLETED.value
