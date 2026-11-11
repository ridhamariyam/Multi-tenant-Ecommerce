"""The platform's system-provided GST rules, and seeding them idempotently.

These are starting points, not tax advice: every rule is seeded UNVERIFIED and
every order line priced by one is flagged until the store reviews it. Only
HSN chapters 61 and 62 (apparel and clothing accessories) are covered; other
goods -- made-ups in chapter 63, footwear, jewellery, bags -- are not
classified here and fall back to the configurable fallback rate.

The migration that creates `gst_default_rules` inserts its own frozen copy of
these rows; this module adds any that are missing (bootstrap, tests) and never
changes a row that exists.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.pricing.constants import RULE_UNVERIFIED, TaxClassification
from app.pricing.models import GstDefaultRule

APPAREL_HSN_PREFIXES = ["61", "62"]

GST_INCEPTION = date(2017, 7, 1)
# The rate rationalisation recommended by the 56th GST Council took effect on
# 22 September 2025; the earlier apparel slabs applied until the day before.
RATIONALISATION_DATE = date(2025, 9, 22)
BEFORE_RATIONALISATION = date(2025, 9, 21)

_PRE_2025_SOURCE = (
    "Notification No. 1/2017-Central Tax (Rate), as amended: apparel of HSN 61/62 at 5% up to "
    "Rs 1,000 sale value per piece, 12% above. Verify against the notified schedule."
)
_2025_SOURCE = (
    "GST rate rationalisation effective 22 Sep 2025 (56th GST Council): apparel of HSN 61/62 at "
    "5% up to Rs 2,500 sale value per piece, 18% above. Verify against the notified schedule."
)
_FALLBACK_SOURCE = (
    "Platform fallback for unclassified goods, set at the standard 18% rate so tax is not "
    "under-collected. It is not a classification: classify the product instead."
)

DEFAULT_RULES: list[dict] = [
    {
        "code": "APPAREL_UPTO_1000",
        "classification": TaxClassification.APPAREL,
        "description": "Apparel (HSN 61/62), sale value up to Rs 1,000 per piece",
        "hsn_prefixes": APPAREL_HSN_PREFIXES,
        "min_unit_value": None,
        "max_unit_value": Decimal("1000.00"),
        "gst_rate": Decimal("5.00"),
        "effective_from": GST_INCEPTION,
        "effective_to": BEFORE_RATIONALISATION,
        "is_fallback": False,
        "source": _PRE_2025_SOURCE,
    },
    {
        "code": "APPAREL_ABOVE_1000",
        "classification": TaxClassification.APPAREL,
        "description": "Apparel (HSN 61/62), sale value above Rs 1,000 per piece",
        "hsn_prefixes": APPAREL_HSN_PREFIXES,
        "min_unit_value": Decimal("1000.00"),
        "max_unit_value": None,
        "gst_rate": Decimal("12.00"),
        "effective_from": GST_INCEPTION,
        "effective_to": BEFORE_RATIONALISATION,
        "is_fallback": False,
        "source": _PRE_2025_SOURCE,
    },
    {
        "code": "APPAREL_UPTO_2500",
        "classification": TaxClassification.APPAREL,
        "description": "Apparel (HSN 61/62), sale value up to Rs 2,500 per piece",
        "hsn_prefixes": APPAREL_HSN_PREFIXES,
        "min_unit_value": None,
        "max_unit_value": Decimal("2500.00"),
        "gst_rate": Decimal("5.00"),
        "effective_from": RATIONALISATION_DATE,
        "effective_to": None,
        "is_fallback": False,
        "source": _2025_SOURCE,
    },
    {
        "code": "APPAREL_ABOVE_2500",
        "classification": TaxClassification.APPAREL,
        "description": "Apparel (HSN 61/62), sale value above Rs 2,500 per piece",
        "hsn_prefixes": APPAREL_HSN_PREFIXES,
        "min_unit_value": Decimal("2500.00"),
        "max_unit_value": None,
        "gst_rate": Decimal("18.00"),
        "effective_from": RATIONALISATION_DATE,
        "effective_to": None,
        "is_fallback": False,
        "source": _2025_SOURCE,
    },
    {
        "code": "FALLBACK_UNCLASSIFIED",
        "classification": TaxClassification.FALLBACK,
        "description": "Unclassified goods -- needs review",
        "hsn_prefixes": [],
        "min_unit_value": None,
        "max_unit_value": None,
        "gst_rate": Decimal("18.00"),
        "effective_from": GST_INCEPTION,
        "effective_to": None,
        "is_fallback": True,
        "source": _FALLBACK_SOURCE,
    },
]


async def ensure_default_rules(session: AsyncSession, *, commit: bool = True) -> int:
    """Insert the default rules that are missing; existing rows are left untouched.

    Returns how many rows were added.
    """
    statement = (
        insert(GstDefaultRule)
        .values([{**rule, "verification_status": RULE_UNVERIFIED} for rule in DEFAULT_RULES])
        .on_conflict_do_nothing(constraint="uq_gst_default_rules_code_effective")
        .returning(GstDefaultRule.id)
    )
    added = len((await session.execute(statement)).all())
    if commit:
        await session.commit()
    return added
