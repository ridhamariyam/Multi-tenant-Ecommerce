"""Reconcile payments created by the other Razorpay lineage.

A database migrated by the `zeen_admin` branch (revision c317fb3ec767) holds
Razorpay ids in `gateway_order_id` / `gateway_payment_id`, guarded by partial
unique indexes and `ck_payments_gateway_*` checks. Moved onto this history
without c51a93d7e204 and 4b7d9a21c63f actually running, it lacks the columns
the Payment model reads, so every query loading a payment fails.

This brings such a database to the schema those two revisions define:

- adds `razorpay_order_id`, `razorpay_payment_id` and
  `razorpay_order_creation_started`, and `uq_payments_razorpay_order_id`;
- copies the existing gateway ids into them (no id is invented) and marks
  creation as started only where a gateway order exists -- what the checkout
  flow itself records for every payment that has one;
- drops the `ck_payments_gateway_*` checks and the partial unique indexes on
  the old columns. The model defines neither, and the checks would reject a
  Razorpay payment marked paid by this code, which never writes the old
  columns.

`gateway_order_id` and `gateway_payment_id` themselves are kept, with their
values, so nothing is lost; dropping them is left as a separate decision.

Every step checks the live schema first, so on a database built by this
history (which already matches the model) the upgrade changes nothing.

Revision ID: f1526859bb6a
Revises: 05e6583c3a6a
Create Date: 2026-10-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f1526859bb6a"
down_revision: Union[str, Sequence[str], None] = "05e6583c3a6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


LEGACY_CHECKS = (
    "ck_payments_gateway_paid_needs_payment_id",
    "ck_payments_gateway_payment_needs_order",
    "ck_payments_gateway_refs_only_for_gateway",
)
LEGACY_INDEXES = ("uq_payments_gateway_order_id", "uq_payments_gateway_payment_id")


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("payments")}
    uniques = {constraint["name"] for constraint in inspector.get_unique_constraints("payments")}
    checks = {constraint["name"] for constraint in inspector.get_check_constraints("payments")}
    indexes = {index["name"] for index in inspector.get_indexes("payments")}

    if "razorpay_order_id" not in columns:
        op.add_column(
            "payments", sa.Column("razorpay_order_id", sa.String(length=64), nullable=True)
        )
    if "razorpay_payment_id" not in columns:
        op.add_column(
            "payments", sa.Column("razorpay_payment_id", sa.String(length=64), nullable=True)
        )
    if "razorpay_order_creation_started" not in columns:
        op.add_column(
            "payments",
            sa.Column(
                "razorpay_order_creation_started",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )

    if "gateway_order_id" in columns and "gateway_payment_id" in columns:
        op.execute(
            """
            UPDATE payments
            SET razorpay_order_id = COALESCE(razorpay_order_id, gateway_order_id),
                razorpay_payment_id = COALESCE(razorpay_payment_id, gateway_payment_id),
                razorpay_order_creation_started =
                    razorpay_order_creation_started OR gateway_order_id IS NOT NULL
            WHERE gateway_order_id IS NOT NULL OR gateway_payment_id IS NOT NULL
            """
        )

    if "uq_payments_razorpay_order_id" not in uniques:
        op.create_unique_constraint(
            op.f("uq_payments_razorpay_order_id"), "payments", ["razorpay_order_id"]
        )

    for name in LEGACY_CHECKS:
        if name in checks:
            op.drop_constraint(op.f(name), "payments", type_="check")
    for name in LEGACY_INDEXES:
        if name in indexes:
            op.drop_index(op.f(name), table_name="payments")


def downgrade() -> None:
    # Nothing to undo safely: on a database built by this history the upgrade
    # was a no-op, and on a reconciled one the added columns now hold the
    # Razorpay ids the application relies on. Dropping them would lose data.
    pass
