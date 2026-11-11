"""The shared, platform-owned library of virtual fashion characters.

No tenant_id on purpose: every brand chooses from the same approved set, and
only platform administrators change it.
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.virtual_models.constants import GENDER_PRESENTATIONS, MODEL_TYPES


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class VirtualModel(IdMixin, TimestampMixin, Base):
    __tablename__ = "virtual_models"

    __table_args__ = (
        UniqueConstraint("name", name="uq_virtual_models_name"),
        CheckConstraint(_in("gender_presentation", GENDER_PRESENTATIONS), name="gender_valid"),
        CheckConstraint(_in("model_type", MODEL_TYPES), name="model_type_valid"),
        # A character brands can pick must have a photo to generate from.
        CheckConstraint("NOT is_active OR image_asset_id IS NOT NULL", name="active_has_image"),
        Index("ix_virtual_models_is_active", "is_active"),
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    gender_presentation: Mapped[str] = mapped_column(String(20), nullable=False)
    model_type: Mapped[str] = mapped_column(String(20), nullable=False)
    available_categories: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=text("'{}'")
    )
    supported_garments: Mapped[list[str]] = mapped_column(
        ARRAY(String(50)), nullable=False, server_default=text("'{}'")
    )
    image_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=True
    )
    # Records who licensed the photographs (commercial use must be cleared).
    license_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class VirtualModelPose(IdMixin, TimestampMixin, Base):
    """Additional photographs (poses) of one character."""

    __tablename__ = "virtual_model_poses"

    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_virtual_model_poses_asset_id"),
        CheckConstraint("sort_order >= 0", name="sort_order_valid"),
        Index("ix_virtual_model_poses_virtual_model_id", "virtual_model_id"),
    )

    virtual_model_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("virtual_models.id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="RESTRICT"), nullable=False
    )
    label: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
