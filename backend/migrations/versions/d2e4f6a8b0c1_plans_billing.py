"""Plans the user chose (Free / Starter ₹999 / Growth ₹2,999) and Razorpay billing fields.

- FREE added; STARTER and GROWTH re-priced; FREE_TRIAL and PRO kept but no
  longer offered (PRO stays on brands that already have it).
- Brands on FREE_TRIAL, and brands with no plan at all, move to FREE.

Revision ID: d2e4f6a8b0c1
Revises: c9d3e1f5a7b2
Create Date: 2026-11-11

"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d2e4f6a8b0c1"
down_revision: Union[str, Sequence[str], None] = "c9d3e1f5a7b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Frozen copy of the plans at this revision.
PLANS = (
    ("FREE", "Free", 0, 0, 25, 1, 1, 0, True,
     {"ai_studio": False, "lookbooks": True, "custom_domains": False, "sheets_export": False}),
    ("STARTER", "Starter", 99900, 0, 500, 1, 3, 1, True,
     {"ai_studio": False, "lookbooks": True, "custom_domains": True, "sheets_export": False}),
    ("GROWTH", "Growth", 299900, 200, None, 1, 10, 2, True,
     {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True}),
    ("PRO", "Pro (legacy)", 0, 1500, None, 1, None, 9, False,
     {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True}),
)  # fmt: skip


def upgrade() -> None:
    op.add_column("subscription_plans", sa.Column("razorpay_plan_id", sa.String(64), nullable=True))
    op.add_column("brand_subscriptions", sa.Column("pending_plan_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_brand_subscriptions_pending_plan_id_subscription_plans",
        "brand_subscriptions", "subscription_plans", ["pending_plan_id"], ["id"], ondelete="SET NULL",
    )
    op.add_column("brand_subscriptions", sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("brand_subscriptions", sa.Column("trial_used", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("brand_subscriptions", sa.Column("past_due_since", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_brand_subscriptions_external_id", "brand_subscriptions", ["external_subscription_id"])

    conn = op.get_bind()
    for code, name, price, credits, products, stores, staff, order, active, features in PLANS:
        conn.execute(
            sa.text(
                "INSERT INTO subscription_plans (id, code, name, monthly_price, monthly_ai_credits,"
                " product_limit, store_limit, staff_limit, sort_order, is_active, features)"
                " VALUES (gen_random_uuid(), :code, :name, :price, :credits, :products, :stores,"
                " :staff, :order, :active, CAST(:features AS jsonb))"
                " ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, monthly_price = EXCLUDED.monthly_price,"
                " monthly_ai_credits = EXCLUDED.monthly_ai_credits, product_limit = EXCLUDED.product_limit,"
                " staff_limit = EXCLUDED.staff_limit, sort_order = EXCLUDED.sort_order,"
                " is_active = EXCLUDED.is_active, features = EXCLUDED.features, razorpay_plan_id = NULL"
            ),
            {"code": code, "name": name, "price": price, "credits": credits, "products": products,
             "stores": stores, "staff": staff, "order": order, "active": active,
             "features": json.dumps(features)},
        )
    conn.execute(sa.text("UPDATE subscription_plans SET is_active = false WHERE code IN ('FREE_TRIAL', 'PRO')"))
    conn.execute(
        sa.text(
            "UPDATE brand_subscriptions SET plan_id = (SELECT id FROM subscription_plans WHERE code = 'FREE'),"
            " status = 'ACTIVE', current_period_start = now(), current_period_end = now() + interval '1 month'"
            " WHERE plan_id = (SELECT id FROM subscription_plans WHERE code = 'FREE_TRIAL')"
        )
    )
    conn.execute(
        sa.text(
            "INSERT INTO brand_subscriptions (id, tenant_id, plan_id, status, current_period_start,"
            " current_period_end, billing_provider)"
            " SELECT gen_random_uuid(), t.id, p.id, 'ACTIVE', now(), now() + interval '1 month', 'manual'"
            " FROM tenants t CROSS JOIN subscription_plans p WHERE p.code = 'FREE'"
            " AND NOT EXISTS (SELECT 1 FROM brand_subscriptions s WHERE s.tenant_id = t.id)"
        )
    )


def downgrade() -> None:
    op.drop_index("ix_brand_subscriptions_external_id", table_name="brand_subscriptions")
    op.drop_column("brand_subscriptions", "past_due_since")
    op.drop_column("brand_subscriptions", "trial_used")
    op.drop_column("brand_subscriptions", "cancel_at_period_end")
    op.drop_constraint("fk_brand_subscriptions_pending_plan_id_subscription_plans", "brand_subscriptions", type_="foreignkey")
    op.drop_column("brand_subscriptions", "pending_plan_id")
    op.drop_column("subscription_plans", "razorpay_plan_id")
