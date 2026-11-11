"""refunds and refresh rotation grace

A payment records the Razorpay refund requested against it, at most one, so
a refund can never be asked for twice. A refresh token records when it was
rotated, which lets a reuse moments later (parallel page loads) be told apart
from a replayed stolen token.

Revision ID: 5b09417602ed
Revises: a8c3f1d9206b
Create Date: 2026-10-15 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5b09417602ed'
down_revision: Union[str, Sequence[str], None] = 'a8c3f1d9206b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('payments', sa.Column('razorpay_refund_id', sa.String(length=64), nullable=True))
    op.create_unique_constraint(
        op.f('uq_payments_razorpay_refund_id'), 'payments', ['razorpay_refund_id']
    )
    op.add_column(
        'refresh_tokens',
        sa.Column('replaced_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('refresh_tokens', 'replaced_at')
    op.drop_constraint(op.f('uq_payments_razorpay_refund_id'), 'payments', type_='unique')
    op.drop_column('payments', 'razorpay_refund_id')
