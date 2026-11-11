"""A tenant is one brand on the platform: its own catalogue, customers and orders.

The platform calls it a *brand*; the code keeps the name `Tenant` because
every brand-owned table already carries `tenant_id` and composite keys on it.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TimestampMixin
from app.tenants.constants import (
    BRAND_STATUSES,
    CURRENCY_CODE_LENGTH,
    DEFAULT_CURRENCY,
    BrandStatus,
)


class Tenant(IdMixin, TimestampMixin, Base):
    __tablename__ = "tenants"

    __table_args__ = (
        CheckConstraint(
            f"currency = upper(currency) AND length(currency) = {CURRENCY_CODE_LENGTH}",
            name="currency_is_iso_4217",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in BRAND_STATUSES) + ")",
            name="status_valid",
        ),
        # A suspended brand is never active; resolution only reads is_active.
        CheckConstraint(
            "status = 'ACTIVE' OR is_active = false", name="inactive_unless_active_status"
        ),
    )

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    currency: Mapped[str] = mapped_column(
        String(CURRENCY_CODE_LENGTH),
        nullable=False,
        default=DEFAULT_CURRENCY,
        server_default=text(f"'{DEFAULT_CURRENCY}'"),
    )

    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BrandStatus.ACTIVE.value,
        server_default=text(f"'{BrandStatus.ACTIVE.value}'"),
    )

    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)

    owner_account_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("merchant_accounts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspension_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TenantDomain(IdMixin, TimestampMixin, Base):
    """A hostname that serves one brand's storefront.

    Platform subdomains (<subdomain>.<platform root>) resolve through the
    store itself and need no row here; this table holds custom domains and
    the domains configured before the platform existed. A domain only serves
    traffic once `verified_at` is set.
    """

    __tablename__ = "tenant_domains"

    __table_args__ = (
        CheckConstraint("domain = lower(domain)", name="domain_is_lowercase"),
        CheckConstraint("length(trim(domain)) > 0", name="domain_not_blank"),
        # At most one primary domain per brand.
        Index(
            "uq_tenant_domains_one_primary",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    domain: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
    )

    # Defaults to "now": rows created by operators (bootstrap, fixtures) are
    # trusted. Domains a brand adds itself are created with None and verified later.
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=func.now(), server_default=func.now()
    )

    is_primary: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    verification_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
