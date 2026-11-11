"""Plans brands subscribe to. Prices are editable by platform operators."""

from __future__ import annotations

from enum import Enum


class SubscriptionStatus(str, Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


SUBSCRIPTION_STATUSES = tuple(s.value for s in SubscriptionStatus)

FEATURES = ("ai_studio", "lookbooks", "custom_domains", "sheets_export")
FEATURE_LABELS = {
    "ai_studio": "AI studio",
    "lookbooks": "Lookbooks",
    "custom_domains": "Your own domain",
    "sheets_export": "Google Sheets order export",
}

# monthly_price is in minor units (paise). None limit = unlimited.
# staff_limit counts everyone on the brand's team, the owner included.
DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "code": "FREE", "name": "Free", "monthly_price": 0, "monthly_ai_credits": 0,
        "product_limit": 25, "store_limit": 1, "staff_limit": 1, "sort_order": 0, "is_active": True,
        "features": {"ai_studio": False, "lookbooks": True, "custom_domains": False, "sheets_export": False},
    },
    {
        "code": "STARTER", "name": "Starter", "monthly_price": 99900, "monthly_ai_credits": 0,
        "product_limit": 500, "store_limit": 1, "staff_limit": 3, "sort_order": 1, "is_active": True,
        "features": {"ai_studio": False, "lookbooks": True, "custom_domains": True, "sheets_export": False},
    },
    {
        "code": "GROWTH", "name": "Growth", "monthly_price": 299900, "monthly_ai_credits": 200,
        "product_limit": None, "store_limit": 1, "staff_limit": 10, "sort_order": 2, "is_active": True,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True},
    },
    # Not offered: the operator's own store and early brands keep it.
    {
        "code": "PRO", "name": "Pro (legacy)", "monthly_price": 0, "monthly_ai_credits": 1500,
        "product_limit": None, "store_limit": 1, "staff_limit": None, "sort_order": 9, "is_active": False,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True},
    },
)  # fmt: skip

NEW_BRAND_PLAN = "FREE"
# What a brand falls back to when a paid subscription lapses.
FALLBACK_PLAN = "FREE"
# Paid plans start with this many days free (once per brand).
TRIAL_DAYS = 14
# A failed renewal keeps paid limits this long while Razorpay retries.
PAST_DUE_GRACE_DAYS = 7
LEGACY_PLAN = "PRO"
