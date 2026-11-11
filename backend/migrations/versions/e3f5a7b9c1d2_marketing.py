"""Marketing consent, abandoned-cart reminders and email campaigns.

Revision ID: e3f5a7b9c1d2
Revises: d2e4f6a8b0c1
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e3f5a7b9c1d2"
down_revision: Union[str, Sequence[str], None] = "d2e4f6a8b0c1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("marketing_opt_in", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("marketing_opt_in_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("marketing_email", sa.String(255), nullable=True))
    op.add_column("carts", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "email_campaigns",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_email_campaigns"),
        sa.Column(
            "tenant_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_email_campaigns_tenant_id_tenants", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("segment", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="DRAFT"),
        sa.Column("recipients", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_email_campaigns_created_by_users", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_email_campaigns_tenant_id", "email_campaigns", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_email_campaigns_tenant_id", table_name="email_campaigns")
    op.drop_table("email_campaigns")
    op.drop_column("carts", "reminder_sent_at")
    op.drop_column("users", "marketing_email")
    op.drop_column("users", "marketing_opt_in_at")
    op.drop_column("users", "marketing_opt_in")
