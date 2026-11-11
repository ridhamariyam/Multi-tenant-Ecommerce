"""align order and payment status checks with the models

The models gained statuses without a migration, so the database still turned
them away: orders and their tracking events (RETURN_REQUESTED, REFUNDED) and
payments (PROCESSING, CANCELLED, REFUND_PENDING, PARTIALLY_REFUNDED, EXPIRED).
Only the allowed lists widen; no row changes.

Revision ID: 64473a74e134
Revises: 02a7a9cb7081
Create Date: 2026-10-12 18:21:52.191911

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '64473a74e134'
down_revision: Union[str, Sequence[str], None] = '02a7a9cb7081'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ORDER = ("PENDING", "CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY",
              "DELIVERED", "CANCELLED", "RETURNED")
_NEW_ORDER = ("PENDING", "CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY",
              "DELIVERED", "CANCELLED", "RETURN_REQUESTED", "RETURNED", "REFUNDED")
_OLD_PAYMENT = ("PENDING", "PAID", "FAILED", "REFUNDED")
_NEW_PAYMENT = ("PENDING", "PROCESSING", "PAID", "FAILED", "CANCELLED", "REFUND_PENDING",
                "REFUNDED", "PARTIALLY_REFUNDED", "EXPIRED")


def _values(statuses: tuple[str, ...]) -> str:
    return ", ".join(f"'{status}'" for status in statuses)


def _set_checks(order: tuple[str, ...], payment: tuple[str, ...]) -> None:
    for table, name, condition in (
        ('orders', 'ck_orders_status_valid', f"status IN ({_values(order)})"),
        ('order_tracking_events', 'ck_order_tracking_events_status_valid',
         f"status IS NULL OR status IN ({_values(order)})"),
        ('payments', 'ck_payments_status_valid', f"status IN ({_values(payment)})"),
    ):
        op.drop_constraint(op.f(name), table, type_='check')
        op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    """Upgrade schema."""
    _set_checks(_NEW_ORDER, _NEW_PAYMENT)


def downgrade() -> None:
    """Downgrade schema."""
    # Rows already in a new status have no old equivalent: refuse rather than
    # rewrite order or payment history.
    new_order = _values(tuple(s for s in _NEW_ORDER if s not in _OLD_ORDER))
    new_payment = _values(tuple(s for s in _NEW_PAYMENT if s not in _OLD_PAYMENT))
    op.execute(
        "DO $$ BEGIN "
        f"IF EXISTS (SELECT 1 FROM orders WHERE status IN ({new_order})) "
        f"OR EXISTS (SELECT 1 FROM order_tracking_events WHERE status IN ({new_order})) "
        f"OR EXISTS (SELECT 1 FROM payments WHERE status IN ({new_payment})) THEN "
        "RAISE EXCEPTION 'rows use statuses this revision added; resolve them before downgrading'; "
        "END IF; END $$"
    )
    _set_checks(_OLD_ORDER, _OLD_PAYMENT)
