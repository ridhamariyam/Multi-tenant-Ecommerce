"""Persist ambiguous Razorpay order creation attempts.

Revision ID: 4b7d9a21c63f
Revises: c51a93d7e204
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4b7d9a21c63f"
down_revision: Union[str, Sequence[str], None] = "c51a93d7e204"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "razorpay_order_creation_started",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    has_started_attempt = op.get_bind().execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM payments "
            "WHERE razorpay_order_creation_started IS TRUE)"
        )
    ).scalar_one()
    if has_started_attempt:
        raise RuntimeError(
            "Cannot downgrade while Razorpay order creation attempts may require reconciliation"
        )

    op.drop_column("payments", "razorpay_order_creation_started")
