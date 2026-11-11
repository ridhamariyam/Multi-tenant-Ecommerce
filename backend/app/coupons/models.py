from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE
from app.coupons.constants import DiscountType
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

_DISCOUNT_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in DiscountType)

class Coupon(IdMixin, TimestampMixin, Base):
    """Discount vouchers usable during checkout."""

    __tablename__ = "coupons"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_coupons_tenant_id_id"),
        UniqueConstraint("tenant_id", "code", name="uq_coupons_tenant_id_code"),
        CheckConstraint(
            f"discount_type IN ({_DISCOUNT_TYPE_VALUES})",
            name="discount_type_valid",
        ),
        CheckConstraint(
            "discount_type = 'FREE_SHIPPING' OR discount_value > 0",
            name="discount_value_positive",
        ),
        CheckConstraint(
            "discount_type NOT IN ('PERCENTAGE', 'BOGO') OR discount_value <= 100",
            name="percentage_max_100",
        ),
        CheckConstraint(
            "discount_type <> 'BOGO' OR (buy_quantity >= 1 AND get_quantity >= 1)",
            name="bogo_has_quantities",
        ),
        CheckConstraint(
            "min_quantity IS NULL OR min_quantity >= 1", name="min_quantity_positive"
        ),
        CheckConstraint(
            "min_order_amount IS NULL OR min_order_amount >= 0",
            name="min_order_amount_not_negative",
        ),
        CheckConstraint(
            "max_discount_amount IS NULL OR max_discount_amount >= 0",
            name="max_discount_amount_not_negative",
        ),
        CheckConstraint(
            "usage_limit IS NULL OR usage_limit >= 0",
            name="usage_limit_not_negative",
        ),
        CheckConstraint(
            "per_customer_usage_limit IS NULL OR per_customer_usage_limit >= 0",
            name="per_customer_usage_limit_not_negative",
        ),
        CheckConstraint("times_used >= 0", name="times_used_not_negative",
        ),
        CheckConstraint(
            "code=upper(code)",
            name="coupon_code_uppercase",
        ),
        CheckConstraint(
            "starts_at IS NULL OR expires_at IS NULL OR starts_at < expires_at",
            name="starts_before_expires"
        ),
        Index("ix_coupons_tenant_id_created_at", "tenant_id", "created_at"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)

    discount_type: Mapped[str] = mapped_column(String(20), nullable=False)

    discount_value: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    min_order_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    max_discount_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    starts_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    usage_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    per_customer_usage_limit: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    times_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Applied at checkout without a code (the code is then just its name).
    is_automatic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Only for a customer with no earlier (non-cancelled) order.
    first_order_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Volume rule: at least this many eligible units in the cart.
    min_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # BOGO: buy this many, get this many discounted.
    buy_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    get_quantity: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Days the coupon works on, 0 = Monday ... 6 = Sunday (shop's local time).
    # NULL = every day.
    valid_weekdays: Mapped[list[int] | None] = mapped_column(JSONB, nullable=True)


class CouponCategory(IdMixin, TenantMixin, TimestampMixin, Base):
    """Limits a coupon to products in these categories (and their sub-categories)."""

    __tablename__ = "coupon_categories"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "coupon_id", "category_id", name="uq_coupon_categories_coupon_category"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "coupon_id"],
            ["coupons.tenant_id", "coupons.id"],
            name="fk_coupon_categories_tenant_coupon_coupons",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "category_id"],
            ["categories.tenant_id", "categories.id"],
            name="fk_coupon_categories_tenant_category_categories",
            ondelete="CASCADE",
        ),
        Index("ix_coupon_categories_tenant_id_coupon_id", "tenant_id", "coupon_id"),
    )

    coupon_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    category_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class CouponUsage(IdMixin, TimestampMixin, Base):
    """Tracks historical coupon redemption per order and customer."""

    __tablename__ = "coupon_usages"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "coupon_id"],
            ["coupons.tenant_id", "coupons.id"],
            name="fk_coupon_usages_tenant_coupon_coupons",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "order_id",
            name="uq_coupon_usages_tenant_id_order_id",
        ),
        CheckConstraint(
            "discount_amount >= 0",
            name="discount_amount_not_negative",
        ),
        Index(
            "ix_coupon_usages_tenant_id_coupon_id_customer_id",
            "tenant_id",
            "coupon_id",
            "customer_id",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    coupon_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
    )

    discount_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

