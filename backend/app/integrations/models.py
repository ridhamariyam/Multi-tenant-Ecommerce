"""Google Sheets order export: each brand's sheet, and which orders are in it."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin

MAX_SPREADSHEET_ID_LENGTH = 128
MAX_WORKSHEET_NAME_LENGTH = 100
DEFAULT_WORKSHEET_NAME = "Orders"


class OrderSheetSettings(IdMixin, TenantMixin, TimestampMixin, Base):
    """The spreadsheet a brand's successful orders are appended to.

    No credentials are stored: the platform's service account writes to any
    spreadsheet the brand has shared with it.
    """

    __tablename__ = "order_sheet_settings"

    __table_args__ = (UniqueConstraint("tenant_id", name="uq_order_sheet_settings_tenant_id"),)

    is_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    spreadsheet_id: Mapped[str | None] = mapped_column(
        String(MAX_SPREADSHEET_ID_LENGTH), nullable=True
    )
    worksheet_name: Mapped[str] = mapped_column(
        String(MAX_WORKSHEET_NAME_LENGTH),
        nullable=False,
        default=DEFAULT_WORKSHEET_NAME,
        server_default=DEFAULT_WORKSHEET_NAME,
    )

    # The outcome of the latest export run, shown on the admin screen.
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", name="fk_order_sheet_settings_updated_by_users", ondelete="SET NULL"),
        nullable=True,
    )


class OrderSheetExport(IdMixin, TenantMixin, Base):
    """One order written to one spreadsheet. Its presence stops a second row."""

    __tablename__ = "order_sheet_exports"

    __table_args__ = (
        # Once per spreadsheet: pointing the brand at a new sheet fills that one too.
        UniqueConstraint(
            "spreadsheet_id", "order_id", name="uq_order_sheet_exports_spreadsheet_order"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_order_sheet_exports_tenant_order_orders",
            ondelete="CASCADE",
        ),
        Index("ix_order_sheet_exports_tenant_id", "tenant_id"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    spreadsheet_id: Mapped[str] = mapped_column(String(MAX_SPREADSHEET_ID_LENGTH), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
