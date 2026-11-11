"""A brand's storefront: its address on the platform, look and publication."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin
from app.stores.constants import DEFAULT_THEME, STORE_THEMES

# Lowercase letters, digits and inner hyphens; one DNS label.
SUBDOMAIN_PATTERN = "^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$"
COLOR_PATTERN = "^#[0-9a-fA-F]{6}$"


class Store(IdMixin, TenantMixin, TimestampMixin, Base):
    __tablename__ = "stores"

    __table_args__ = (
        # One storefront per brand for now; plans may lift this later.
        UniqueConstraint("tenant_id", name="uq_stores_tenant"),
        UniqueConstraint("subdomain", name="uq_stores_subdomain"),
        CheckConstraint(f"subdomain ~ '{SUBDOMAIN_PATTERN}'", name="subdomain_format"),
        CheckConstraint(
            "theme IN (" + ", ".join(f"'{t}'" for t in STORE_THEMES) + ")", name="theme_valid"
        ),
        CheckConstraint(
            f"primary_color IS NULL OR primary_color ~ '{COLOR_PATTERN}'",
            name="primary_color_hex",
        ),
        CheckConstraint(
            f"secondary_color IS NULL OR secondary_color ~ '{COLOR_PATTERN}'",
            name="secondary_color_hex",
        ),
        CheckConstraint(
            "published = false OR published_at IS NOT NULL", name="published_has_timestamp"
        ),
    )

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    subdomain: Mapped[str] = mapped_column(String(63), nullable=False)
    theme: Mapped[str] = mapped_column(
        String(30), nullable=False, default=DEFAULT_THEME, server_default=text(f"'{DEFAULT_THEME}'")
    )
    logo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    favicon_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    secondary_color: Mapped[str | None] = mapped_column(String(7), nullable=True)
    published: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
