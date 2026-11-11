import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.payments.constants import PaymentProvider, PaymentPurpose, PaymentStatus

_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in PaymentStatus)
_PROVIDER_VALUES = ", ".join(f"'{provider.value}'" for provider in PaymentProvider)
_PURPOSE_VALUES = ", ".join(f"'{purpose.value}'" for purpose in PaymentPurpose)


class Payment(IdMixin, TenantMixin, TimestampMixin, Base):
    """What is owed on one order, and whether it has been collected."""

    __tablename__ = "payments"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_payments_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_payments_tenant_order_orders",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint(f"provider IN ({_PROVIDER_VALUES})", name="provider_valid"),
        CheckConstraint("amount >= 0", name="amount_not_negative"),
        CheckConstraint(f"purpose IN ({_PURPOSE_VALUES})", name="purpose_valid"),
        Index(
            "uq_payments_one_paid_per_order_purpose",
            "tenant_id",
            "order_id",
            "purpose",
            unique=True,
            postgresql_where=text("status = 'PAID'"),
        ),
        Index("ix_payments_tenant_id_order_id", "tenant_id", "order_id"),
        Index("ix_payments_tenant_id_status", "tenant_id", "status"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentStatus.PENDING.value
    )

    provider: Mapped[str] = mapped_column(
        String(20), nullable=False, default=PaymentProvider.COD.value
    )
    remitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    remittance_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    purpose: Mapped[str] = mapped_column(
        String(10), nullable=False, default=PaymentPurpose.FULL.value,
        server_default=PaymentPurpose.FULL.value,
    )
    razorpay_order_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Set and committed before making the external create-order request. If
    # its response is lost, retries must not create a second gateway order.
    razorpay_order_creation_started: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    razorpay_refund_id: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
