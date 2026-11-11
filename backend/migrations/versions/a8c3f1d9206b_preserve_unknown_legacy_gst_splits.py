"""preserve legacy tax totals without inventing GST classification

Revision ID: a8c3f1d9206b
Revises: 64473a74e134
Create Date: 2026-10-14

Historical orders without a frozen GST classification cannot be reliably
labelled intra-state or inter-state. Keep their tax_amount and represent the
component split as unknown (all component amounts zero, gst_type NULL).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "a8c3f1d9206b"
down_revision: Union[str, Sequence[str], None] = "64473a74e134"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_orders_gst_split_matches_tax"), "orders", type_="check")
    # The preceding historical revision assigned every legacy tax total to
    # IGST. Clear that unsupported classification while preserving tax_amount.
    # No current tenant or buyer location is used to infer historical tax.
    op.execute(
        "UPDATE orders SET cgst_amount = 0, sgst_amount = 0, igst_amount = 0 "
        "WHERE gst_type IS NULL"
    )
    op.create_check_constraint(
        op.f("ck_orders_gst_split_matches_tax"),
        "orders",
        "(gst_type IS NULL AND cgst_amount = 0 AND sgst_amount = 0 AND igst_amount = 0) "
        "OR (gst_type IS NOT NULL AND cgst_amount + sgst_amount + igst_amount = tax_amount)",
    )


def downgrade() -> None:
    # The prior constraint cannot represent a nonzero total with an unknown
    # split. Refuse to downgrade while such historical records remain rather
    # than relabel or discard their tax amounts.
    op.execute(
        "DO $$ BEGIN "
        "IF EXISTS (SELECT 1 FROM orders WHERE gst_type IS NULL AND tax_amount <> 0) THEN "
        "RAISE EXCEPTION 'unknown GST split has nonzero tax; resolve records before downgrade'; "
        "END IF; END $$"
    )
    op.drop_constraint(op.f("ck_orders_gst_split_matches_tax"), "orders", type_="check")
    op.create_check_constraint(
        op.f("ck_orders_gst_split_matches_tax"),
        "orders",
        "cgst_amount + sgst_amount + igst_amount = tax_amount",
    )
