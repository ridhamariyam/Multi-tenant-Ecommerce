"""Email campaigns a brand sends to customers who agreed to marketing email."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


class CampaignStatus:
    DRAFT = "DRAFT"
    SENT = "SENT"


class EmailCampaign(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "email_campaigns"
    __table_args__ = (Index("ix_email_campaigns_tenant_id", "tenant_id"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # {"kind": "ALL" | "ORDERED_WITHIN" | "NO_ORDERS" | "TAG", "days": int, "tag": str}
    segment: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=CampaignStatus.DRAFT, server_default=CampaignStatus.DRAFT)
    recipients: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_email_campaigns_created_by_users", ondelete="SET NULL"),
        nullable=True,
    )
