import uuid

from sqlalchemy import ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID  # type: ignore
from sqlalchemy.orm import Mapped, mapped_column  # type: ignore

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


class Wishlist(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "wishlists"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_wishlists_tenant_id_id"),
        ForeignKeyConstraint(
            ["tenant_id", "customer_id"],
            ["users.tenant_id", "users.id"],
            name="fk_wishlists_tenant_customer_users",
            ondelete="CASCADE",
        ),
        Index(
            "uq_wishlists_one_per_customer",
            "tenant_id",
            "customer_id",
            unique=True,
        ),
    )

    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)


class WishlistItem(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "wishlist_items"

    __table_args__ = (
        UniqueConstraint("wishlist_id", "variant_id", name="uq_wishlist_items_wishlist_variant"),
        ForeignKeyConstraint(
            ["tenant_id", "wishlist_id"],
            ["wishlists.tenant_id", "wishlists.id"],
            name="fk_wishlist_items_tenant_wishlist_wishlists",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "variant_id"],
            ["product_variants.tenant_id", "product_variants.id"],
            name="fk_wishlist_items_tenant_variant_product_variants",
            ondelete="CASCADE",
        ),
        Index("ix_wishlist_items_tenant_id_wishlist_id", "tenant_id", "wishlist_id"),
    )

    wishlist_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    variant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
