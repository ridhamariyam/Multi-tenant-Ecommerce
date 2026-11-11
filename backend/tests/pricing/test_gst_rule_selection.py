"""Choosing a line's GST rate from the system defaults, without a database.

The rules are the seeded ones (app/pricing/defaults.py); the arithmetic
examples are arithmetic, not a ruling on how any real product is taxed.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.exceptions import ConflictError
from app.pricing.constants import TaxSource, TaxVerification
from app.pricing.defaults import DEFAULT_RULES
from app.pricing.gst import TaxableLine, compute_tax
from app.pricing.models import GstDefaultRule, TaxRateConfiguration
from app.pricing.tax_engine import TaxEngine, TaxLineInput, TaxProfile, select_band

TODAY = date(2026, 10, 30)
BEFORE_2025_CHANGE = date(2025, 9, 1)


def rules_on(on: date) -> list[GstDefaultRule]:
    return [
        GstDefaultRule(id=uuid.uuid4(), verification_status="UNVERIFIED", **rule)
        for rule in DEFAULT_RULES
        if rule["effective_from"] <= on
        and (rule["effective_to"] is None or rule["effective_to"] >= on)
    ]


def line(**overrides) -> TaxLineInput:
    values = {
        "key": "k",
        "product_id": uuid.uuid4(),
        "category_id": uuid.uuid4(),
        "quantity": 1,
        "amount": Decimal("0.00"),
    }
    values.update(overrides)
    return TaxLineInput(**values)


def resolve(unit_value: str, *, on: date = TODAY, approved=({}, {}), **kwargs):
    profile = kwargs.pop("profile", TaxProfile())
    engine = TaxEngine(session=None, tenant_id=uuid.uuid4())  # resolve() never queries
    return engine.resolve(
        line(**kwargs), Decimal(unit_value), profile=profile, rules=rules_on(on), approved=approved
    )


@pytest.mark.parametrize(
    ("price", "rate", "code"),
    [
        ("2499.99", "5.00", "APPAREL_UPTO_2500"),
        ("2500.00", "5.00", "APPAREL_UPTO_2500"),
        ("2500.01", "18.00", "APPAREL_ABOVE_2500"),
        ("999.00", "5.00", "APPAREL_UPTO_2500"),
        ("4999.00", "18.00", "APPAREL_ABOVE_2500"),
    ],
)
def test_the_2500_threshold_is_per_piece_and_inclusive(price, rate, code):
    resolution = resolve(price, product_hsn="6204")

    assert resolution.rate == Decimal(rate)
    assert resolution.rule_code == code
    assert resolution.source == TaxSource.SYSTEM_DEFAULT


def test_rules_follow_the_effective_date():
    """Before 22 Sep 2025 the apparel slabs were 5% up to 1,000 and 12% above."""
    old = resolve("2000.00", product_hsn="6204", on=BEFORE_2025_CHANGE)
    new = resolve("2000.00", product_hsn="6204")

    assert (old.rate, old.rule_code) == (Decimal("12.00"), "APPAREL_ABOVE_1000")
    assert (new.rate, new.rule_code) == (Decimal("5.00"), "APPAREL_UPTO_2500")


def test_a_category_hsn_classifies_the_product():
    resolution = resolve("3000.00", category_hsn="6109")

    assert resolution.rate == Decimal("18.00")
    assert resolution.hsn_code == "6109"


def test_without_an_hsn_the_store_classification_is_assumed_and_flagged():
    resolution = resolve("2000.00")

    assert resolution.rate == Decimal("5.00")
    assert resolution.verification == TaxVerification.AWAITING_VERIFICATION
    assert "assumed" in resolution.reason


def test_a_reviewed_store_has_its_defaults_verified():
    resolution = resolve("2000.00", product_hsn="6204", profile=TaxProfile(defaults_reviewed=True))

    assert resolution.verification == TaxVerification.VERIFIED


def test_an_hsn_outside_the_rules_falls_back_for_review():
    """7117 (imitation jewellery) is not apparel: no default applies."""
    resolution = resolve("500.00", product_hsn="7117")

    assert resolution.source == TaxSource.FALLBACK
    assert resolution.verification == TaxVerification.NEEDS_REVIEW
    assert resolution.rate == Decimal("18.00")
    assert resolution.rule_code == "FALLBACK_UNCLASSIFIED"


def test_no_assumed_classification_falls_back():
    resolution = resolve("500.00", profile=TaxProfile(default_classification=None))

    assert resolution.source == TaxSource.FALLBACK


def test_the_tenant_fallback_rate_replaces_the_system_one():
    resolution = resolve(
        "500.00", product_hsn="7117", profile=TaxProfile(fallback_rate=Decimal("3.00"))
    )

    assert resolution.rate == Decimal("3.00")
    assert resolution.rule is None


def test_no_fallback_at_all_is_refused_not_guessed():
    engine = TaxEngine(session=None, tenant_id=uuid.uuid4())
    without_fallback = [rule for rule in rules_on(TODAY) if not rule.is_fallback]

    with pytest.raises(ConflictError):
        engine.resolve(
            line(product_hsn="7117"), Decimal("500.00"), profile=TaxProfile(),
            rules=without_fallback, approved=({}, {}),
        )


def test_a_manual_rate_beats_the_default_but_stays_unverified():
    resolution = resolve("3000.00", product_hsn="6204", product_rate=Decimal("12.00"))

    assert resolution.rate == Decimal("12.00")
    assert resolution.source == TaxSource.MANUAL
    assert resolution.verification == TaxVerification.AWAITING_VERIFICATION


def test_a_product_rate_beats_its_category_rate():
    resolution = resolve(
        "3000.00", product_rate=Decimal("12.00"), category_rate=Decimal("5.00")
    )

    assert resolution.rate == Decimal("12.00")


def test_an_approved_override_beats_everything():
    product_id = uuid.uuid4()
    mapping = TaxRateConfiguration(
        id=uuid.uuid4(), product_id=product_id, hsn_code="620442", gst_rate=Decimal("5.00")
    )

    resolution = resolve(
        "3000.00", product_id=product_id, product_rate=Decimal("12.00"),
        approved=({product_id: mapping}, {}),
    )

    assert resolution.rate == Decimal("5.00")
    assert resolution.source == TaxSource.APPROVED_OVERRIDE
    assert resolution.verification == TaxVerification.VERIFIED
    assert resolution.configuration_id == mapping.id


def test_a_disabled_store_charges_nothing():
    resolution = resolve("3000.00", product_hsn="6204", profile=TaxProfile(enabled=False))

    assert resolution.rate == Decimal("0.00")
    assert resolution.source == TaxSource.DISABLED


@pytest.mark.parametrize(
    ("inclusive_price", "rate"),
    [
        ("2625.00", "5.00"),  # 2,500.00 + 5%: exactly at the threshold
        ("2600.00", "5.00"),  # 2,476.19 before GST
        ("2625.01", "18.00"),  # just over: no band is consistent, the higher one applies
        ("2950.01", "18.00"),  # 2,500.01 + 18%
    ],
)
def test_an_inclusive_price_is_banded_on_its_value_before_gst(inclusive_price, rate):
    rule = select_band(
        [r for r in rules_on(TODAY) if r.classification == "APPAREL"],
        Decimal(inclusive_price),
        inclusive=True,
    )

    assert rule.gst_rate == Decimal(rate)


def test_exclusive_arithmetic_adds_gst_on_top():
    """Rs 2,000 before GST at 5%: Rs 100 tax, Rs 2,100 total."""
    result = compute_tax(
        [TaxableLine(key="k", amount=Decimal("2000.00"), rate=Decimal("5.00"))],
        discount=Decimal("0.00"), charges=Decimal("0.00"), default_rate=Decimal("5.00"),
        active=True, gst_type=None,
    )

    assert result.lines["k"].taxable == Decimal("2000.00")
    assert result.tax_amount == Decimal("100.00")


def test_inclusive_arithmetic_extracts_gst_instead_of_adding_it():
    """Rs 2,000 including 5%: Rs 95.24 tax inside a Rs 1,904.76 taxable value."""
    result = compute_tax(
        [
            TaxableLine(
                key="k", amount=Decimal("2000.00"), rate=Decimal("5.00"), prices_include_tax=True
            )
        ],
        discount=Decimal("0.00"), charges=Decimal("0.00"), default_rate=Decimal("5.00"),
        active=True, gst_type=None,
    )

    assert result.lines["k"].taxable == Decimal("1904.76")
    assert result.lines["k"].tax == Decimal("95.24")
    assert result.included_tax == Decimal("95.24")
