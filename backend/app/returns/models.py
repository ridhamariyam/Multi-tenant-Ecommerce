"""The store's own list of return reasons, chosen when an order is marked returned."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

MAX_REASON_LENGTH = 100
MAX_RETURN_NOTE_LENGTH = 500


class ReturnReason(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "return_reasons"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_return_reasons_tenant_id_id"),
        Index(
            "uq_return_reasons_tenant_label",
            "tenant_id",
            text("lower(label)"),
            unique=True,
        ),
    )

    label: Mapped[str] = mapped_column(String(MAX_REASON_LENGTH), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
