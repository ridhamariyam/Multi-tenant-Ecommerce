"""Cash-on-delivery controls: one settings row per tenant and a phone blacklist."""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE
from app.cod.constants import MAX_REASON_LENGTH, BlacklistSource
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

_SOURCE_VALUES = ", ".join(f"'{source.value}'" for source in BlacklistSource)


class CodSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """A tenant's COD rules. No row at all means COD is on with no limits or fee."""

    __tablename__ = "cod_settings"

    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_cod_settings_tenant_id"),
        CheckConstraint(
            "min_order_amount IS NULL OR min_order_amount >= 0",
            name="min_order_amount_not_negative",
        ),
        CheckConstraint(
            "max_order_amount IS NULL OR max_order_amount >= 0",
            name="max_order_amount_not_negative",
        ),
        CheckConstraint(
            "min_order_amount IS NULL OR max_order_amount IS NULL"
            " OR min_order_amount <= max_order_amount",
            name="order_limits_ordered",
        ),
        CheckConstraint("fee_amount >= 0", name="fee_amount_not_negative"),
        CheckConstraint(
            "advance_amount IS NULL OR advance_amount > 0", name="advance_amount_positive"
        ),
        CheckConstraint(
            "auto_blacklist_threshold IS NULL OR auto_blacklist_threshold >= 1",
            name="auto_blacklist_threshold_positive",
        ),
    )

    # Master switch for the whole shop.
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # COD only for orders whose total sits inside these bounds.
    min_order_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )
    max_order_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    # Handling fee added to every COD order.
    fee_amount: Mapped[Decimal] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=False, default=Decimal("0.00")
    )

    # Paid before the order is confirmed (e.g. 100 by UPI); NULL = no advance.
    advance_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(PRICE_PRECISION, PRICE_SCALE), nullable=True
    )

    # After this many RETURNED (undelivered) COD orders, a phone is blacklisted.
    auto_blacklist_threshold: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CodBlacklistEntry(IdMixin, TenantMixin, TimestampMixin, Base):
    """A phone number that may only order prepaid."""

    __tablename__ = "cod_blacklist"

    __table_args__ = (
        UniqueConstraint("tenant_id", "phone", name="uq_cod_blacklist_tenant_phone"),
        CheckConstraint(r"phone ~ '^\+[1-9][0-9]{7,14}$'", name="phone_is_e164"),
        CheckConstraint(f"source IN ({_SOURCE_VALUES})", name="source_valid"),
    )

    phone: Mapped[str] = mapped_column(String(16), nullable=False)

    reason: Mapped[str | None] = mapped_column(String(MAX_REASON_LENGTH), nullable=True)

    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default=BlacklistSource.MANUAL.value
    )
