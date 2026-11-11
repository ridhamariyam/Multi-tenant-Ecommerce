"""Add Razorpay identifiers to payments.

Revision ID: c51a93d7e204
Revises: 27f827e24c4a
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c51a93d7e204"
down_revision: Union[str, Sequence[str], None] = "27f827e24c4a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "payments", sa.Column("razorpay_order_id", sa.String(length=64), nullable=True)
    )
    op.add_column(
        "payments", sa.Column("razorpay_payment_id", sa.String(length=64), nullable=True)
    )
    op.create_unique_constraint(
        op.f("uq_payments_razorpay_order_id"),
        "payments",
        ["razorpay_order_id"],
    )

    op.drop_constraint(
        op.f("ck_payments_provider_valid"), "payments", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"),
        "payments",
        "provider IN ('COD', 'RAZORPAY')",
    )


def downgrade() -> None:
    # A downgrade must never silently erase gateway identifiers or payment
    # records. Existing COD-only data is safe to preserve through this change.
    has_razorpay_data = op.get_bind().execute(
        sa.text(
            """
            SELECT EXISTS (
                SELECT 1
                FROM payments
                WHERE provider = 'RAZORPAY'
                   OR razorpay_order_id IS NOT NULL
                   OR razorpay_payment_id IS NOT NULL
            )
            """
        )
    ).scalar_one()
    if has_razorpay_data:
        raise RuntimeError(
            "Cannot downgrade payment gateway support while Razorpay payment "
            "records or identifiers exist"
        )

    op.drop_constraint(
        op.f("ck_payments_provider_valid"), "payments", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_payments_provider_valid"), "payments", "provider IN ('COD')"
    )
    op.drop_constraint(
        op.f("uq_payments_razorpay_order_id"), "payments", type_="unique"
    )
    op.drop_column("payments", "razorpay_payment_id")
    op.drop_column("payments", "razorpay_order_id")
