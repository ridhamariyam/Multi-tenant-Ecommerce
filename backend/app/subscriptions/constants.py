"""Plans. Prices are placeholders until a billing provider is connected."""

from __future__ import annotations

from enum import Enum


class SubscriptionStatus(str, Enum):
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    CANCELLED = "CANCELLED"


SUBSCRIPTION_STATUSES = tuple(s.value for s in SubscriptionStatus)

FEATURES = ("ai_studio", "lookbooks", "custom_domains")

# monthly_price is in minor units (paise). None limit = unlimited.
DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "code": "FREE_TRIAL", "name": "Free Trial", "monthly_price": 0, "monthly_ai_credits": 20,
        "product_limit": 25, "store_limit": 1, "staff_limit": 2, "sort_order": 0,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": False},
    },
    {
        "code": "STARTER", "name": "Starter", "monthly_price": 199900, "monthly_ai_credits": 100,
        "product_limit": 200, "store_limit": 1, "staff_limit": 3, "sort_order": 1,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": False},
    },
    {
        "code": "GROWTH", "name": "Growth", "monthly_price": 499900, "monthly_ai_credits": 400,
        "product_limit": 2000, "store_limit": 1, "staff_limit": 10, "sort_order": 2,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True},
    },
    {
        "code": "PRO", "name": "Pro", "monthly_price": 999900, "monthly_ai_credits": 1500,
        "product_limit": None, "store_limit": 1, "staff_limit": None, "sort_order": 3,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True},
    },
)  # fmt: skip

NEW_BRAND_PLAN = "FREE_TRIAL"
TRIAL_DAYS = 14
# Brands that existed before plans were introduced keep working without limits.
LEGACY_PLAN = "PRO"
