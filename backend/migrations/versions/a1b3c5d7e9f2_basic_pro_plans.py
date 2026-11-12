"""Two plans: Basic (₹4,999 + GST) and Pro (₹8,999 + GST), 14-day Basic trial.

- The operator's unlisted unlimited plan is renamed PRO -> PLATFORM so the
  code PRO can be the new paid plan (brands on it keep it).
- FREE / STARTER / GROWTH are retired (is_active = false, rows kept because
  subscriptions and ledger references point at them).
- Brands move: FREE -> BASIC on a fresh 14-day trial (no payment details),
  STARTER -> BASIC, GROWTH -> PRO, keeping status and billing.

Additive for old code except the plan codes; downgrade restores the codes.

Revision ID: a1b3c5d7e9f2
Revises: f4a6b8c0d2e3
Create Date: 2026-11-12

"""
import json
import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b3c5d7e9f2"
down_revision: Union[str, Sequence[str], None] = "f4a6b8c0d2e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BASIC = {
    "code": "BASIC", "name": "Basic", "monthly_price": 499900, "monthly_ai_credits": 0,
    "product_limit": 500, "store_limit": 1, "staff_limit": 3, "sort_order": 0,
    "features": {"ai_studio": False, "lookbooks": True, "custom_domains": True, "sheets_export": False},
}  # fmt: skip
PRO = {
    "code": "PRO", "name": "Pro", "monthly_price": 899900, "monthly_ai_credits": 200,
    "product_limit": None, "store_limit": 1, "staff_limit": 10, "sort_order": 1,
    "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True},
}  # fmt: skip


def _insert(conn, plan: dict) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO subscription_plans (id, code, name, monthly_price, currency, monthly_ai_credits,"
            " product_limit, store_limit, staff_limit, features, is_active, sort_order)"
            " VALUES (:id, :code, :name, :monthly_price, 'INR', :monthly_ai_credits, :product_limit,"
            " :store_limit, :staff_limit, CAST(:features AS jsonb), true, :sort_order)"
            " ON CONFLICT (code) DO NOTHING"
        ),
        {**plan, "id": str(uuid.uuid4()), "features": json.dumps(plan["features"])},
    )


def _move(conn, old: str, new: str) -> None:
    conn.execute(
        sa.text(
            "UPDATE brand_subscriptions SET plan_id = (SELECT id FROM subscription_plans WHERE code = :new)"
            " WHERE plan_id = (SELECT id FROM subscription_plans WHERE code = :old)"
        ),
        {"old": old, "new": new},
    )


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE subscription_plans SET code = 'PLATFORM', name = 'Platform (internal)', is_active = false,"
        " sort_order = 9 WHERE code = 'PRO'"
    ))  # fmt: skip
    _insert(conn, BASIC)
    _insert(conn, PRO)
    # Free brands start the Basic trial now (manual = no payment details yet).
    conn.execute(sa.text(
        "UPDATE brand_subscriptions SET status = 'TRIALING', billing_provider = 'manual',"
        " external_subscription_id = NULL, cancel_at_period_end = false, past_due_since = NULL,"
        " trial_used = true, current_period_start = now(), current_period_end = now() + interval '14 days'"
        " WHERE plan_id = (SELECT id FROM subscription_plans WHERE code = 'FREE')"
    ))  # fmt: skip
    _move(conn, "FREE", "BASIC")
    _move(conn, "STARTER", "BASIC")
    _move(conn, "GROWTH", "PRO")
    conn.execute(sa.text(
        "UPDATE subscription_plans SET is_active = false, razorpay_plan_id = NULL"
        " WHERE code IN ('FREE', 'STARTER', 'GROWTH')"
    ))  # fmt: skip
    conn.execute(sa.text(
        "UPDATE brand_subscriptions SET pending_plan_id = NULL WHERE pending_plan_id IN"
        " (SELECT id FROM subscription_plans WHERE code IN ('FREE', 'STARTER', 'GROWTH'))"
    ))  # fmt: skip


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text(
        "UPDATE subscription_plans SET is_active = true WHERE code IN ('FREE', 'STARTER', 'GROWTH')"
    ))  # fmt: skip
    _move(conn, "BASIC", "STARTER")
    conn.execute(sa.text(
        "UPDATE brand_subscriptions SET pending_plan_id = NULL WHERE pending_plan_id IN"
        " (SELECT id FROM subscription_plans WHERE code IN ('BASIC', 'PRO'))"
    ))  # fmt: skip
    _move(conn, "PRO", "GROWTH")
    conn.execute(sa.text("DELETE FROM subscription_plans WHERE code IN ('BASIC', 'PRO')"))
    conn.execute(sa.text(
        "UPDATE subscription_plans SET code = 'PRO', name = 'Pro (legacy)' WHERE code = 'PLATFORM'"
    ))  # fmt: skip
