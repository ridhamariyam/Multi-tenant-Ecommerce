"""Every file the platform stores on a brand's (or the platform's) behalf."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.media.constants import MEDIA_KINDS, REVIEW_STATUSES, VISIBILITIES
from app.models.base import Base, IdMixin, TimestampMixin


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class MediaAsset(IdMixin, TimestampMixin, Base):
    """One stored object. Brand assets carry tenant_id; platform assets do not.

    Keys are brand-scoped and server-chosen:
      <tenant>/<hex>.<ext>                     public brand media
      private/<tenant>/ai/<job>/<n>.<ext>      AI output awaiting review
      platform/virtual-models/<model>/<hex>.<ext>
    """

    __tablename__ = "media_assets"

    __table_args__ = (
        UniqueConstraint("storage_key", name="uq_media_assets_storage_key"),
        UniqueConstraint("tenant_id", "id", name="uq_media_assets_tenant_id_id"),
        CheckConstraint(_in("kind", MEDIA_KINDS), name="kind_valid"),
        CheckConstraint(_in("visibility", VISIBILITIES), name="visibility_valid"),
        CheckConstraint(
            f"review_status IS NULL OR {_in('review_status', REVIEW_STATUSES)}",
            name="review_status_valid",
        ),
        # Only the character library is platform-owned; everything else is a brand's.
        CheckConstraint(
            "(tenant_id IS NULL) = (kind = 'VIRTUAL_MODEL')", name="owner_matches_kind"
        ),
        CheckConstraint("visibility = 'PRIVATE' OR url IS NOT NULL", name="public_has_url"),
        CheckConstraint(
            "(kind = 'AI_GENERATED') = (review_status IS NOT NULL)",
            name="review_only_for_ai",
        ),
        CheckConstraint("size_bytes > 0", name="size_positive"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_media_assets_tenant_product_products",
            ondelete="SET NULL (product_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "source_asset_id"],
            ["media_assets.tenant_id", "media_assets.id"],
            name="fk_media_assets_tenant_source_media_assets",
            ondelete="CASCADE",
        ),
        Index("ix_media_assets_tenant_id_kind", "tenant_id", "kind"),
        Index("ix_media_assets_tenant_id_product_id", "tenant_id", "product_id"),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["ai_generation_jobs.tenant_id", "ai_generation_jobs.id"],
            name="fk_media_assets_tenant_job_ai_generation_jobs",
            ondelete="SET NULL (job_id)",
            use_alter=True,
        ),
        UniqueConstraint("tenant_id", "job_id", "output_index", name="uq_media_assets_job_output"),
        Index("ix_media_assets_job_id", "job_id"),
    )

    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    visibility: Mapped[str] = mapped_column(String(10), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    # Stable public URL for PUBLIC assets; PRIVATE ones are signed on demand.
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # The AI job that produced it, and which of its outputs (0..3) this is;
    # unique together, so a repeated callback cannot store an output twice.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    output_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # For THUMBNAIL / STOREFRONT copies: the asset they derive from.
    source_asset_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(10), nullable=True)
