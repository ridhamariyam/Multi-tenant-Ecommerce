"""Billing webhook event log and ordering guard (F13).

Additive only: the previous release ignores the new column and table, so a
rollback of the code keeps working on this schema.

Revision ID: f4a6b8c0d2e3
Revises: e3f5a7b9c1d2
Create Date: 2026-11-12

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f4a6b8c0d2e3"
down_revision: Union[str, Sequence[str], None] = "e3f5a7b9c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("brand_subscriptions", sa.Column("provider_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_billing_webhook_events"),
        sa.Column("provider_event_id", sa.String(100), nullable=False),
        sa.Column("event", sa.String(60), nullable=False),
        sa.Column("external_subscription_id", sa.String(200), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("outcome", sa.String(12), nullable=False),
        sa.Column("reason", sa.String(200), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("provider_event_id", name="uq_billing_webhook_events_provider_event_id"),
    )
    op.create_index(
        "ix_billing_webhook_events_subscription", "billing_webhook_events", ["external_subscription_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_subscription", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
    op.drop_column("brand_subscriptions", "provider_event_at")
