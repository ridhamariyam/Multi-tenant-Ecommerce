import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


class CartStatus(str, Enum):
    ACTIVE = "ACTIVE"
    CONVERTED = "CONVERTED"
    # Untouched for longer than the retention period; its items are gone.
    EXPIRED = "EXPIRED"


GUEST_TOKEN_HASH_LENGTH = 64


_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in CartStatus)


class Cart(IdMixin, TenantMixin, TimestampMixin, Base):
    """A working basket, owned by a customer or by a guest's cart token.

    One ACTIVE cart per customer per tenant. A guest cart has no customer;
    it is found by the SHA-256 of the token the guest's device holds.
    """

    __tablename__ = "carts"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_carts_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_carts_tenant_customer_users",
            ondelete="CASCADE",
        ),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint(
            "(customer_id IS NULL) <> (guest_token_hash IS NULL)",
            name="owned_by_customer_or_guest",
        ),
        Index(
            "uq_carts_guest_token_hash",
            "guest_token_hash",
            unique=True,
            postgresql_where=text("guest_token_hash IS NOT NULL"),
        ),
        Index("ix_carts_status_last_activity_at", "status", "last_activity_at"),
        Index(
            "uq_carts_one_active_per_customer",
            "tenant_id",
            "customer_id",
            unique=True,
            postgresql_where=text("status = 'ACTIVE'"),
        ),
    )

    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    guest_token_hash: Mapped[str | None] = mapped_column(
        String(GUEST_TOKEN_HASH_LENGTH), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CartStatus.ACTIVE.value
    )

    # Bumped on every change; a cart idle past the retention period expires.
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class CartItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """A variant and its quantity; catalogue data is read live, never copied in."""

    __tablename__ = "cart_items"

    __table_args__ = (
        UniqueConstraint("cart_id", "variant_id", name="uq_cart_items_cart_variant"),
        ForeignKeyConstraint(
            ["tenant_id", "cart_id"],
            ["carts.tenant_id", "carts.id"],
            name="fk_cart_items_tenant_cart_carts",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_cart_items_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_cart_items_tenant_id_cart_id", "tenant_id", "cart_id"),
    )

    cart_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
