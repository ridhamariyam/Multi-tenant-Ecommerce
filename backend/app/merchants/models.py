"""Platform-wide merchant identities.

Shoppers keep their per-brand `users` rows: a customer of one brand is
unknown to every other brand. A merchant account is the person behind one or
more brands; it reaches a brand's data only through an active `BrandMember`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.merchants.constants import ACCOUNT_STATUSES, AccountStatus
from app.models.base import Base, IdMixin, TimestampMixin


class MerchantAccount(IdMixin, TimestampMixin, Base):
    __tablename__ = "merchant_accounts"

    __table_args__ = (
        CheckConstraint("email = lower(email)", name="email_is_lowercase"),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in ACCOUNT_STATUSES) + ")",
            name="status_valid",
        ),
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=AccountStatus.ACTIVE.value,
        server_default=text(f"'{AccountStatus.ACTIVE.value}'"),
    )
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status == AccountStatus.ACTIVE.value


class MerchantRefreshToken(IdMixin, TimestampMixin, Base):
    """One issued platform refresh token, stored hashed, rotated on use."""

    __tablename__ = "merchant_refresh_tokens"

    __table_args__ = (Index("ix_merchant_refresh_tokens_account", "account_id"),)

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
