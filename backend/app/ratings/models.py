from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    and_,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.ratings.constants import (
    MAX_ALT_TEXT_LENGTH,
    MAX_IMAGE_URL_LENGTH,
    MAX_RATING,
    MAX_TITLE_LENGTH,
    MIN_RATING,
)


class Review(IdMixin, TimestampMixin, Base):
    """One shopper's verdict on a product, written once per purchase."""

    __tablename__ = "reviews"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_reviews_tenant_id_id"),
        CheckConstraint(
            f"rating >= {MIN_RATING} AND rating <= {MAX_RATING}",
            name="ck_reviews_rating_range",
        ),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "product_id",
            name="uq_tenant_user_product_review",
        ),
        # A review outlives the product, the account and the order it came from.
        # The subset spelling matters: a bare SET NULL on a composite key nulls
        # every referencing column, tenant_id included, and that aborts the
        # delete against a NOT NULL column.
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_reviews_tenant_product_products",
            ondelete="SET NULL (product_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_reviews_tenant_user_users",
            ondelete="SET NULL (user_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_reviews_tenant_order_orders",
            ondelete="SET NULL (order_id)",
        ),
        Index("ix_reviews_tenant_id_product_id", "tenant_id", "product_id"),
        Index("ix_reviews_tenant_id_user_id", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str | None] = mapped_column(String(MAX_TITLE_LENGTH), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_verified_purchase: Mapped[bool] = mapped_column(nullable=False, default=False)
    is_approved: Mapped[bool] = mapped_column(nullable=False, default=True)

    images: Mapped[list[ReviewImage]] = relationship(
        "ReviewImage",
        primaryjoin=lambda: and_(
            Review.id == ReviewImage.review_id,
            Review.tenant_id == ReviewImage.tenant_id,
        ),
        foreign_keys=lambda: [ReviewImage.review_id, ReviewImage.tenant_id],
        back_populates="review",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ReviewImage(IdMixin, TenantMixin, TimestampMixin, Base):
    """A photo attached to a review."""

    __tablename__ = "review_images"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_review_images_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "review_id"],
            ["reviews.tenant_id", "reviews.id"],
            name="fk_review_images_tenant_review_reviews",
            ondelete="CASCADE",
        ),
        Index("ix_review_images_tenant_id_review_id", "tenant_id", "review_id"),
    )

    review_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
    )

    image_url: Mapped[str] = mapped_column(String(MAX_IMAGE_URL_LENGTH), nullable=False)
    alt_text: Mapped[str | None] = mapped_column(
        String(MAX_ALT_TEXT_LENGTH), nullable=True
    )

    review: Mapped[Review] = relationship(
        "Review",
        primaryjoin=lambda: and_(
            ReviewImage.review_id == Review.id,
            ReviewImage.tenant_id == Review.tenant_id,
        ),
        foreign_keys=lambda: [ReviewImage.review_id, ReviewImage.tenant_id],
        back_populates="images",
    )


class ReviewRequestStatus(str, Enum):
    PENDING = "PENDING"  # waiting for send_after
    SENT = "SENT"  # the customer has been asked
    COMPLETED = "COMPLETED"  # every product on the order has a review
    CANCELLED = "CANCELLED"


_REQUEST_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ReviewRequestStatus)


class ReviewRequest(IdMixin, TenantMixin, TimestampMixin, Base):
    """An automatic "how was it?" prompt, one per delivered order."""

    __tablename__ = "review_requests"

    __table_args__ = (
        UniqueConstraint("tenant_id", "order_id", name="uq_review_requests_tenant_order"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_review_requests_tenant_order_orders",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_review_requests_tenant_customer_users",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_REQUEST_STATUS_VALUES})", name="status_valid"),
        Index("ix_review_requests_status_send_after", "status", "send_after"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=ReviewRequestStatus.PENDING.value
    )

    send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
