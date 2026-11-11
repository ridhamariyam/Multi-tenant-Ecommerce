"""System GST default rules, tenant GST defaults, and a fuller order-line tax snapshot.

- `gst_default_rules`: platform-wide, tenant-free rules (classification, HSN
  prefixes, per-piece value band, effective dates), seeded UNVERIFIED. The seed
  is a frozen copy of app/pricing/defaults.py at this revision and uses
  ON CONFLICT DO NOTHING, so re-running it never duplicates or rewrites a row.
- `gst_settings`: `gst_enabled`, `default_classification`, `fallback_gst_rate`
  and the tenant's review of the defaults. Existing rows keep every value they
  have; the new columns take the platform defaults (GST on, apparel assumed for
  products without an HSN code, system fallback rate, not reviewed).
- `orders.tax_review_required` and per-line CGST/SGST/IGST, rule reference,
  source and verification on `order_items`. All nullable or defaulted: orders
  placed before this keep exactly the tax they were charged.

Revision ID: 5d8e2b7c41a9
Revises: f1526859bb6a
Create Date: 2026-10-30

"""
import uuid
from datetime import date
from decimal import Decimal
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5d8e2b7c41a9"
down_revision: Union[str, Sequence[str], None] = "f1526859bb6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PRE_2025 = (
    "Notification No. 1/2017-Central Tax (Rate), as amended: apparel of HSN 61/62 at 5% up to "
    "Rs 1,000 sale value per piece, 12% above. Verify against the notified schedule."
)
_2025 = (
    "GST rate rationalisation effective 22 Sep 2025 (56th GST Council): apparel of HSN 61/62 at "
    "5% up to Rs 2,500 sale value per piece, 18% above. Verify against the notified schedule."
)
_FALLBACK = (
    "Platform fallback for unclassified goods, set at the standard 18% rate so tax is not "
    "under-collected. It is not a classification: classify the product instead."
)

# code, classification, description, prefixes, min, max, rate, from, to, fallback, source
_RULES = [
    ("APPAREL_UPTO_1000", "APPAREL", "Apparel (HSN 61/62), sale value up to Rs 1,000 per piece",
     ["61", "62"], None, "1000.00", "5.00", "2017-07-01", "2025-09-21", False, _PRE_2025),
    ("APPAREL_ABOVE_1000", "APPAREL", "Apparel (HSN 61/62), sale value above Rs 1,000 per piece",
     ["61", "62"], "1000.00", None, "12.00", "2017-07-01", "2025-09-21", False, _PRE_2025),
    ("APPAREL_UPTO_2500", "APPAREL", "Apparel (HSN 61/62), sale value up to Rs 2,500 per piece",
     ["61", "62"], None, "2500.00", "5.00", "2025-09-22", None, False, _2025),
    ("APPAREL_ABOVE_2500", "APPAREL", "Apparel (HSN 61/62), sale value above Rs 2,500 per piece",
     ["61", "62"], "2500.00", None, "18.00", "2025-09-22", None, False, _2025),
    ("FALLBACK_UNCLASSIFIED", "FALLBACK", "Unclassified goods -- needs review",
     [], None, None, "18.00", "2017-07-01", None, True, _FALLBACK),
]


def upgrade() -> None:
    op.create_table(
        "gst_default_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(60), nullable=False),
        sa.Column("classification", sa.String(40), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("hsn_prefixes", postgresql.ARRAY(sa.String(8)), nullable=False, server_default="{}"),
        sa.Column("min_unit_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("max_unit_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("gst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("verification_status", sa.String(20), nullable=False, server_default="UNVERIFIED"),
        sa.Column("source", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_gst_default_rules")),
        sa.UniqueConstraint("code", "effective_from", name="uq_gst_default_rules_code_effective"),
        sa.CheckConstraint("gst_rate >= 0 AND gst_rate <= 100", name=op.f("ck_gst_default_rules_gst_rate_in_range")),
        sa.CheckConstraint(
            "min_unit_value IS NULL OR max_unit_value IS NULL OR max_unit_value > min_unit_value",
            name=op.f("ck_gst_default_rules_value_band_ordered"),
        ),
        sa.CheckConstraint(
            "effective_to IS NULL OR effective_to >= effective_from",
            name=op.f("ck_gst_default_rules_dates_ordered"),
        ),
        sa.CheckConstraint(
            "verification_status IN ('UNVERIFIED', 'VERIFIED')",
            name=op.f("ck_gst_default_rules_verification_status_valid"),
        ),
    )
    op.create_index(
        "ix_gst_default_rules_classification", "gst_default_rules", ["classification", "effective_from"]
    )

    connection = op.get_bind()
    insert = sa.text(
        "INSERT INTO gst_default_rules (id, code, classification, description, hsn_prefixes, "
        "min_unit_value, max_unit_value, gst_rate, effective_from, effective_to, is_fallback, "
        "verification_status, source) VALUES (:id, :code, :classification, :description, "
        ":prefixes, :min, :max, :rate, :start, :end, :fallback, 'UNVERIFIED', :source) "
        "ON CONFLICT ON CONSTRAINT uq_gst_default_rules_code_effective DO NOTHING"
    ).bindparams(
        sa.bindparam("prefixes", type_=postgresql.ARRAY(sa.String(8))),
        sa.bindparam("min", type_=sa.Numeric(12, 2)),
        sa.bindparam("max", type_=sa.Numeric(12, 2)),
        sa.bindparam("end", type_=sa.Date()),
    )
    for code, classification, description, prefixes, low, high, rate, start, end, fallback, source in _RULES:
        connection.execute(insert, {
            "id": uuid.uuid4(), "code": code, "classification": classification,
            "description": description, "prefixes": prefixes,
            "min": Decimal(low) if low else None, "max": Decimal(high) if high else None,
            "rate": Decimal(rate), "start": date.fromisoformat(start),
            "end": date.fromisoformat(end) if end else None,
            "fallback": fallback, "source": source,
        })

    op.add_column("gst_settings", sa.Column("gst_enabled", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("gst_settings", sa.Column("default_classification", sa.String(40), nullable=True, server_default="APPAREL"))
    op.add_column("gst_settings", sa.Column("fallback_gst_rate", sa.Numeric(5, 2), nullable=True))
    op.add_column("gst_settings", sa.Column("defaults_reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("gst_settings", sa.Column("defaults_reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_gst_settings_defaults_reviewed_by_users", "gst_settings", "users",
        ["defaults_reviewed_by_id"], ["id"], ondelete="SET NULL",
    )

    op.add_column("orders", sa.Column("tax_review_required", sa.Boolean(), nullable=False, server_default="false"))

    op.add_column("order_items", sa.Column("cgst_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("order_items", sa.Column("sgst_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("order_items", sa.Column("igst_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("order_items", sa.Column("tax_rule_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("order_items", sa.Column("tax_rule_code", sa.String(60), nullable=True))
    op.add_column("order_items", sa.Column("tax_source", sa.String(20), nullable=True))
    op.add_column("order_items", sa.Column("tax_verification", sa.String(30), nullable=True))
    op.create_foreign_key(
        "fk_order_items_tax_rule", "order_items", "gst_default_rules",
        ["tax_rule_id"], ["id"], ondelete="RESTRICT",
    )
    op.create_index("ix_order_items_tax_rule_id", "order_items", ["tax_rule_id"])


def downgrade() -> None:
    op.drop_index("ix_order_items_tax_rule_id", table_name="order_items")
    op.drop_constraint("fk_order_items_tax_rule", "order_items", type_="foreignkey")
    for column in (
        "tax_verification", "tax_source", "tax_rule_code", "tax_rule_id",
        "igst_amount", "sgst_amount", "cgst_amount",
    ):
        op.drop_column("order_items", column)

    op.drop_column("orders", "tax_review_required")

    op.drop_constraint("fk_gst_settings_defaults_reviewed_by_users", "gst_settings", type_="foreignkey")
    for column in (
        "defaults_reviewed_by_id", "defaults_reviewed_at", "fallback_gst_rate",
        "default_classification", "gst_enabled",
    ):
        op.drop_column("gst_settings", column)

    op.drop_index("ix_gst_default_rules_classification", table_name="gst_default_rules")
    op.drop_table("gst_default_rules")
