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

# monthly_price is in minor units (paise), BEFORE GST: brands are charged
# monthly_price + PLATFORM_GST_PERCENT (18%). None limit = unlimited.
# staff_limit counts everyone on the brand's team, the owner included.
DEFAULT_PLANS: tuple[dict, ...] = (
    {
        "code": "BASIC", "name": "Basic", "monthly_price": 499900, "monthly_ai_credits": 0,
        "product_limit": 500, "store_limit": 1, "staff_limit": 3, "sort_order": 0, "is_active": True,
        "features": {"ai_studio": False, "lookbooks": True, "custom_domains": True, "sheets_export": False},
    },
    {
        "code": "PRO", "name": "Pro", "monthly_price": 899900, "monthly_ai_credits": 200,
        "product_limit": None, "store_limit": 1, "staff_limit": 10, "sort_order": 1, "is_active": True,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True},
    },
    # Not offered: the platform operator's own store.
    {
        "code": "PLATFORM", "name": "Platform (internal)", "monthly_price": 0, "monthly_ai_credits": 1500,
        "product_limit": None, "store_limit": 1, "staff_limit": None, "sort_order": 9, "is_active": False,
        "features": {"ai_studio": True, "lookbooks": True, "custom_domains": True, "sheets_export": True},
    },
)  # fmt: skip

# Every new brand starts here, on a free trial with no payment details.
NEW_BRAND_PLAN = "BASIC"
TRIAL_DAYS = 14
# A renewal that failed (or a trial whose Razorpay mandate has not been
# charged yet) keeps the store open this long while Razorpay retries.
PAST_DUE_GRACE_DAYS = 7
LEGACY_PLAN = "PLATFORM"
# Plans retired on 2026-11-12; rows are kept (is_active = false) for history.
RETIRED_PLANS = ("FREE", "STARTER", "GROWTH")
