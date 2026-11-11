"""Who may act for a brand, and as what."""

from __future__ import annotations

import uuid

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.brands.constants import BRAND_ROLES, MEMBER_STATUSES, MemberStatus
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


class BrandMember(IdMixin, TenantMixin, TimestampMixin, Base):
    """A merchant account's membership of one brand.

    `user_id` is the brand's own ADMIN/STAFF `users` row for this member. The
    existing admin endpoints, audit log and CMS authorship all key on that
    row, so a membership reuses them unchanged. The composite key keeps the
    user inside the same brand.
    """

    __tablename__ = "brand_members"

    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", name="uq_brand_members_tenant_account"),
        UniqueConstraint("tenant_id", "user_id", name="uq_brand_members_tenant_user"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_brand_members_tenant_user",
            ondelete="CASCADE",
        ),
        CheckConstraint(
            "role IN (" + ", ".join(f"'{r}'" for r in BRAND_ROLES) + ")", name="role_valid"
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in MEMBER_STATUSES) + ")",
            name="status_valid",
        ),
        Index("ix_brand_members_account", "account_id"),
        # Exactly one owner per brand.
        Index(
            "uq_brand_members_one_owner",
            "tenant_id",
            unique=True,
            postgresql_where=text("role = 'OWNER' AND status = 'ACTIVE'"),
        ),
    )

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=MemberStatus.ACTIVE.value,
        server_default=text(f"'{MemberStatus.ACTIVE.value}'"),
    )
