import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.auth.constants import UserRole, UserStatus
from app.models.base import Base, IdMixin, TimestampMixin

_ROLE_VALUES = ", ".join(f"'{role.value}'" for role in UserRole)
_STATUS_VALUES = ", ".join(f"'{status.value}'" for status in UserStatus)

_E164_SQL = r"phone ~ '^\+[1-9][0-9]{7,14}$'"


class User(IdMixin, TimestampMixin, Base):
    __tablename__ = "users"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
        UniqueConstraint("tenant_id", "phone", name="uq_users_tenant_phone"),
        Index(
            "uq_users_tenant_staff_email",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("role IN ('ADMIN', 'STAFF')"),
        ),
        CheckConstraint(f"role IN ({_ROLE_VALUES})", name="role_valid"),
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint("email IS NULL OR email = lower(email)", name="email_is_lowercase"),
        # Staff created through a brand membership sign in by email on the
        # platform and may have no phone; any phone that is stored is E.164.
        CheckConstraint(f"phone IS NULL OR {_E164_SQL}", name="phone_is_e164"),
        CheckConstraint(
            "(role = 'CUSTOMER') = (password_hash IS NULL)",
            name="password_matches_role",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    phone: Mapped[str | None] = mapped_column(String(16), nullable=True)

    email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    name: Mapped[str | None] = mapped_column(String(150), nullable=True)

    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserRole.CUSTOMER.value,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=UserStatus.ACTIVE.value,
    )

    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # STAFF only: granted admin permissions. NULL = legacy staff access
    # (see app/auth/permissions.py); ADMIN ignores it.
    permissions: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # CUSTOMER only: labels the store gives a customer (VIP, frequent returner...).
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    # CUSTOMER only: set when the store blocks this customer from placing new
    # orders (as account or guest). Past orders and history are untouched.
    order_blocked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    order_block_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # Marketing email consent (campaigns, cart reminders). Order emails need none.
    marketing_opt_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    marketing_opt_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Where marketing goes when the account has no email of its own (given at guest checkout).
    marketing_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    @property
    def is_active(self) -> bool:
        return self.status == UserStatus.ACTIVE.value

class UserIdentity(IdMixin, TimestampMixin, Base):
    __tablename__ = "user_identities"

    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            ondelete="CASCADE",
            name="fk_user_identities_tenant_user",
        ),
        UniqueConstraint(
            "tenant_id",
            "provider",
            "subject",
            name="uq_user_identities_tenant_provider_subject",
        ),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "provider",
            name="uq_user_identities_tenant_user_provider",
        ),
        Index("ix_user_identities_tenant_user", "tenant_id", "user_id"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    subject: Mapped[str] = mapped_column(String(320), nullable=False)
