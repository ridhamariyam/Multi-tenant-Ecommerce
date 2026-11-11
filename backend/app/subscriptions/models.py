"""Subscription plans and each brand's current plan."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.subscriptions.constants import SUBSCRIPTION_STATUSES


class SubscriptionPlan(IdMixin, TimestampMixin, Base):
    __tablename__ = "subscription_plans"

    __table_args__ = (
        UniqueConstraint("code", name="uq_subscription_plans_code"),
        CheckConstraint("monthly_price >= 0", name="price_valid"),
        CheckConstraint("monthly_ai_credits >= 0", name="credits_valid"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    monthly_price: Mapped[int] = mapped_column(Integer, nullable=False)  # minor units
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR", server_default=text("'INR'"))
    monthly_ai_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    product_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    store_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    staff_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'"))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=text("true"))
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class BrandSubscription(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "brand_subscriptions"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_brand_subscriptions_tenant"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in SUBSCRIPTION_STATUSES) + ")",
            name="status_valid",
        ),
        CheckConstraint("current_period_end > current_period_start", name="period_valid"),
    )

    plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_plans.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    current_period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # "manual" until a billing provider is connected: no money moves.
    billing_provider: Mapped[str] = mapped_column(
        String(30), nullable=False, default="manual", server_default=text("'manual'")
    )
    external_subscription_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
