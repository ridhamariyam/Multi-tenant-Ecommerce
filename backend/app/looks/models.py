"""Interactive lookbooks: a hero image with product pins."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

LOOK_STATUSES = ("DRAFT", "PUBLISHED", "ARCHIVED")


class Look(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "looks"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_looks_tenant_id_id"),
        UniqueConstraint("tenant_id", "slug", name="uq_looks_tenant_id_slug"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in LOOK_STATUSES) + ")", name="status_valid"
        ),
        CheckConstraint(
            "status <> 'PUBLISHED' OR (published_at IS NOT NULL AND cover_asset_id IS NOT NULL)",
            name="published_complete",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "cover_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_looks_tenant_cover_asset_media_assets",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "background_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_looks_tenant_background_asset_media_assets",
            ondelete="RESTRICT",
        ),
        Index("ix_looks_tenant_id_status", "tenant_id", "status"),
    )

    title: Mapped[str] = mapped_column(String(150), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The hero image the pins sit on: a public asset of this brand.
    cover_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    background_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="DRAFT", server_default=text("'DRAFT'"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))


class LookItem(IdMixin, TenantMixin, TimestampMixin, Base):
    """One product pinned on a look. Coordinates are fractions of the image (0..1)."""

    __tablename__ = "look_items"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_look_items_tenant_id_id"),
        UniqueConstraint("look_id", "product_id", name="uq_look_items_look_product"),
        CheckConstraint("hotspot_x >= 0 AND hotspot_x <= 1", name="hotspot_x_range"),
        CheckConstraint("hotspot_y >= 0 AND hotspot_y <= 1", name="hotspot_y_range"),
        CheckConstraint("position >= 0", name="position_valid"),
        ForeignKeyConstraint(
            ["tenant_id", "look_id"],
            ["looks.tenant_id", "looks.id"],
            name="fk_look_items_tenant_look_looks",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_look_items_tenant_product_products",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "media_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_look_items_tenant_media_asset_media_assets",
            ondelete="SET NULL (media_asset_id)",
        ),
        Index("ix_look_items_tenant_id_look_id", "tenant_id", "look_id"),
    )

    look_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # Optional close-up for this piece (e.g. its approved AI image).
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    hotspot_x: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
    hotspot_y: Mapped[float] = mapped_column(Numeric(6, 5), nullable=False)
