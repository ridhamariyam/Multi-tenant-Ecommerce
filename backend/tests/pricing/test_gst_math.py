"""The GST engine on its own: rates, splits, rounding and the single-rate guarantee."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.core.money import money
from app.orders.constants import GstType
from app.pricing.gst import TaxableLine, compute_tax, state_code_for, supply_type

D = Decimal


def _lines(*specs):
    return [TaxableLine(key=i, amount=D(a), rate=D(r)) for i, (a, r) in enumerate(specs)]


@pytest.mark.parametrize(
    ("amounts", "discount", "charges"),
    [
        (["999.00", "999.00"], "0.00", "100.00"),
        (["333.33", "666.67", "10.01"], "99.99", "49.50"),
        (["1.00"], "0.50", "0.00"),
    ],
)
def test_one_rate_matches_the_old_single_percentage(amounts, discount, charges):
    result = compute_tax(
        _lines(*[(a, "18.00") for a in amounts]),
        discount=D(discount),
        charges=D(charges),
        default_rate=D("18.00"),
        active=True,
        gst_type=None,
    )

    old = money((sum(map(D, amounts)) - D(discount) + D(charges)) * D("18.00") / 100)
    assert result.tax_amount == old


def test_mixed_rates_tax_each_group_and_charges_at_the_default():
    result = compute_tax(
        _lines(("1000.00", "5.00"), ("1000.00", "12.00")),
        discount=D("0.00"),
        charges=D("100.00"),
        default_rate=D("18.00"),
        active=True,
        gst_type=GstType.INTER_STATE,
    )

    assert result.lines[0].tax == D("50.00")
    assert result.lines[1].tax == D("120.00")
    assert result.charges_tax == D("18.00")
    assert result.tax_amount == D("188.00")
    assert result.igst == D("188.00")


def test_a_discount_is_spread_across_lines():
    result = compute_tax(
        _lines(("300.00", "5.00"), ("100.00", "5.00")),
        discount=D("40.00"),
        charges=D("0.00"),
        default_rate=D("5.00"),
        active=True,
        gst_type=None,
    )

    assert result.lines[0].discount == D("30.00")
    assert result.lines[1].discount == D("10.00")
    assert result.lines[0].taxable == D("270.00")


def test_intra_state_halves_add_back_up_exactly():
    result = compute_tax(
        _lines(("100.01", "5.00")),
        discount=D("0.00"),
        charges=D("0.00"),
        default_rate=D("5.00"),
        active=True,
        gst_type=GstType.INTRA_STATE,
    )

    assert result.cgst + result.sgst == result.tax_amount
    assert result.igst == D("0.00")


def test_tax_inclusive_price_extracts_tax_without_increasing_the_gross_total():
    line = TaxableLine("inclusive", D("118.00"), D("18.00"), "1234", True)
    result = compute_tax(
        [line], discount=D("0.00"), charges=D("0.00"), default_rate=D("0.00"),
        active=True, gst_type=GstType.INTRA_STATE,
    )

    assert result.lines["inclusive"].taxable == D("100.00")
    assert result.lines["inclusive"].tax == D("18.00")
    assert result.included_tax == D("18.00")
    assert result.tax_amount - result.included_tax == D("0.00")
    assert result.cgst + result.sgst == result.tax_amount


def test_tax_inclusive_discount_and_mixed_rates_use_each_products_rate():
    result = compute_tax(
        [
            TaxableLine("five", D("105.00"), D("5.00"), "1111", True),
            TaxableLine("twelve", D("112.00"), D("12.00"), "2222", True),
        ],
        discount=D("21.70"), charges=D("0.00"), default_rate=D("0.00"),
        active=True, gst_type=GstType.INTER_STATE,
    )

    assert result.lines["five"].discount == D("10.50")
    assert result.lines["twelve"].discount == D("11.20")
    assert result.lines["five"].taxable == D("90.00")
    assert result.lines["twelve"].taxable == D("90.00")
    assert result.lines["five"].tax == D("4.50")
    assert result.lines["twelve"].tax == D("10.80")
    assert result.igst == D("15.30")


def test_inactive_tax_charges_nothing():
    result = compute_tax(
        _lines(("500.00", "12.00")),
        discount=D("0.00"),
        charges=D("50.00"),
        default_rate=D("18.00"),
        active=False,
        gst_type=GstType.INTRA_STATE,
    )

    assert result.tax_amount == D("0.00")


@pytest.mark.parametrize(
    ("value", "code"),
    [("Kerala", "32"), (" karnataka ", "29"), ("32", "32"), ("Orissa", "21"), ("Atlantis", None)],
)
def test_state_codes(value, code):
    assert state_code_for(value) == code


def test_supply_type():
    assert supply_type("29", "Karnataka") is GstType.INTRA_STATE
    assert supply_type("29", "Kerala") is GstType.INTER_STATE
    assert supply_type(None, "Kerala") is GstType.INTER_STATE
    assert supply_type("29", None) is None
