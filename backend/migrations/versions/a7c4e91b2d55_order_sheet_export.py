"""Google Sheets order export: per-store sheet settings and an export log.

Revision ID: a7c4e91b2d55
Revises: c3d9f4a6e1b2
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7c4e91b2d55"
down_revision: Union[str, Sequence[str], None] = "c3d9f4a6e1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "order_sheet_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenants.id", name="fk_order_sheet_settings_tenant_id_tenants", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_sheet_settings"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("spreadsheet_id", sa.String(128), nullable=True),
        sa.Column("worksheet_name", sa.String(100), nullable=False, server_default="Orders"),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", name="fk_order_sheet_settings_updated_by_users", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", name="uq_order_sheet_settings_tenant_id"),
    )

    op.create_table(
        "order_sheet_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenants.id", name="fk_order_sheet_exports_tenant_id_tenants", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_order_sheet_exports"),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("spreadsheet_id", sa.String(128), nullable=False),
        sa.Column("exported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "spreadsheet_id", "order_id", name="uq_order_sheet_exports_spreadsheet_order"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "order_id"],
            ["orders.tenant_id", "orders.id"],
            name="fk_order_sheet_exports_tenant_order_orders",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_order_sheet_exports_tenant_id", "order_sheet_exports", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_order_sheet_exports_tenant_id", table_name="order_sheet_exports")
    op.drop_table("order_sheet_exports")
    op.drop_table("order_sheet_settings")
