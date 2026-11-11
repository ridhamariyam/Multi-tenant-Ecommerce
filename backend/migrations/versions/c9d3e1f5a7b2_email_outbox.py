"""Email outbox and merchant password reset links.

Revision ID: c9d3e1f5a7b2
Revises: b8e2f0c4d6a1
Create Date: 2026-11-11

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c9d3e1f5a7b2"
down_revision: Union[str, Sequence[str], None] = "b8e2f0c4d6a1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamps():
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "email_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_email_outbox"),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", name="fk_email_outbox_tenant_id_tenants", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False),
        sa.Column("to_address", sa.String(255), nullable=False),
        sa.Column("from_name", sa.String(150), nullable=False),
        sa.Column("reply_to", sa.String(255), nullable=True),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("text_body", sa.Text(), nullable=False),
        sa.Column("html_body", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("send_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("dedupe_key", name="uq_email_outbox_dedupe_key"),
    )
    op.create_index("ix_email_outbox_due", "email_outbox", ["status", "send_after"])
    op.create_index("ix_email_outbox_tenant_id", "email_outbox", ["tenant_id"])

    op.create_table(
        "merchant_password_resets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_merchant_password_resets"),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("merchant_accounts.id", name="fk_merchant_password_resets_account", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.UniqueConstraint("token_hash", name="uq_merchant_password_resets_token_hash"),
    )


def downgrade() -> None:
    op.drop_table("merchant_password_resets")
    op.drop_index("ix_email_outbox_tenant_id", table_name="email_outbox")
    op.drop_index("ix_email_outbox_due", table_name="email_outbox")
    op.drop_table("email_outbox")
