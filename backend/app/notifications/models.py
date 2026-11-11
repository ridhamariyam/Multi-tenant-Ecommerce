"""Outgoing email, written in the same transaction as the event that causes it
and sent afterwards by the scheduler, with retries."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin


class EmailStatus:
    PENDING = "PENDING"
    SENT = "SENT"
    FAILED = "FAILED"  # gave up after EMAIL_MAX_ATTEMPTS


class OutboxEmail(IdMixin, TimestampMixin, Base):
    __tablename__ = "email_outbox"
    __table_args__ = (
        # One email per (kind, subject record): re-running a job never sends twice.
        UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
        Index("ix_email_outbox_due", "status", "send_after"),
        Index("ix_email_outbox_tenant_id", "tenant_id"),
    )

    # Null for platform mail (merchant password resets).
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", name="fk_email_outbox_tenant_id_tenants", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str] = mapped_column(String(150), nullable=False)
    reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    text_body: Mapped[str] = mapped_column(Text, nullable=False)
    html_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=EmailStatus.PENDING, server_default=EmailStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    send_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MerchantPasswordReset(IdMixin, TimestampMixin, Base):
    __tablename__ = "merchant_password_resets"
    __table_args__ = (UniqueConstraint("token_hash", name="uq_merchant_password_resets_token_hash"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_accounts.id", name="fk_merchant_password_resets_account", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
