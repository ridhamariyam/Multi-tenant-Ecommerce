"""Each brand's own Razorpay account (keys stored encrypted).

Revision ID: b8e2f0c4d6a1
Revises: a7c4e91b2d55
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8e2f0c4d6a1"
down_revision: Union[str, Sequence[str], None] = "a7c4e91b2d55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "payment_gateway_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "tenants.id", name="fk_payment_gateway_accounts_tenant_id_tenants", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_payment_gateway_accounts"),
        sa.Column("provider", sa.String(20), nullable=False, server_default="RAZORPAY"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("key_secret_encrypted", sa.String(500), nullable=False),
        sa.Column("webhook_secret_encrypted", sa.String(500), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey(
                "users.id", name="fk_payment_gateway_accounts_updated_by_users", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("tenant_id", name="uq_payment_gateway_accounts_tenant_id"),
    )


def downgrade() -> None:
    op.drop_table("payment_gateway_accounts")
