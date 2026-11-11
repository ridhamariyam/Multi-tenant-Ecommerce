"""GST arithmetic: per-rate tax, CGST/SGST vs IGST, and line-level figures for invoices.

Prices are tax-exclusive (tax is added on top), matching the existing checkout.
With one rate everywhere the result is exactly the old single-percentage tax:
money((subtotal - discount + charges) * rate / 100).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from app.core.money import ZERO, money
from app.orders.constants import GstType
from app.pricing.constants import PERCENT

# GST state codes (first two digits of a GSTIN).
STATE_CODES: dict[str, str] = {
    "01": "Jammu and Kashmir",
    "02": "Himachal Pradesh",
    "03": "Punjab",
    "04": "Chandigarh",
    "05": "Uttarakhand",
    "06": "Haryana",
    "07": "Delhi",
    "08": "Rajasthan",
    "09": "Uttar Pradesh",
    "10": "Bihar",
    "11": "Sikkim",
    "12": "Arunachal Pradesh",
    "13": "Nagaland",
    "14": "Manipur",
    "15": "Mizoram",
    "16": "Tripura",
    "17": "Meghalaya",
    "18": "Assam",
    "19": "West Bengal",
    "20": "Jharkhand",
    "21": "Odisha",
    "22": "Chhattisgarh",
    "23": "Madhya Pradesh",
    "24": "Gujarat",
    "26": "Dadra and Nagar Haveli and Daman and Diu",
    "27": "Maharashtra",
    "29": "Karnataka",
    "30": "Goa",
    "31": "Lakshadweep",
    "32": "Kerala",
    "33": "Tamil Nadu",
    "34": "Puducherry",
    "35": "Andaman and Nicobar Islands",
    "36": "Telangana",
    "37": "Andhra Pradesh",
    "38": "Ladakh",
}

_ALIASES = {
    "orissa": "21",
    "pondicherry": "34",
    "new delhi": "07",
    "nct of delhi": "07",
    "j&k": "01",
    "jammu & kashmir": "01",
    "daman and diu": "26",
    "dadra and nagar haveli": "26",
    "andaman & nicobar islands": "35",
}

_BY_NAME = {name.lower(): code for code, name in STATE_CODES.items()}


def state_code_for(value: str | None) -> str | None:
    """'Kerala', 'kerala ' or '32' -> '32'. Unknown -> None."""
    if not value:
        return None
    key = value.strip().lower()
    if key in STATE_CODES:
        return key
    return _BY_NAME.get(key) or _ALIASES.get(key)


@dataclass
class TaxableLine:
    key: object
    amount: Decimal  # line subtotal before any discount
    rate: Decimal
    hsn_code: str | None = None
    prices_include_tax: bool = False


@dataclass
class LineTax:
    discount: Decimal
    taxable: Decimal
    rate: Decimal
    tax: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    hsn_code: str | None


@dataclass
class TaxResult:
    tax_amount: Decimal = ZERO
    cgst: Decimal = ZERO
    sgst: Decimal = ZERO
    igst: Decimal = ZERO
    gst_type: GstType | None = None
    lines: dict = field(default_factory=dict)
    charges_taxable: Decimal = ZERO
    charges_tax: Decimal = ZERO
    charges_rate: Decimal = ZERO
    included_tax: Decimal = ZERO


def _spread(total: Decimal, weights: list[Decimal]) -> list[Decimal]:
    """Split `total` in proportion to `weights`, rounded, the last share taking the remainder."""
    if not weights:
        return []
    whole = sum(weights, ZERO)
    if whole == ZERO:
        return [ZERO] * (len(weights) - 1) + [total]
    shares = [money(total * weight / whole) for weight in weights[:-1]]
    return [*shares, total - sum(shares, ZERO)]


def split_tax(tax: Decimal, gst_type: GstType | str | None) -> tuple[Decimal, Decimal, Decimal]:
    """(CGST, SGST, IGST) for a tax amount: halves within a state, all IGST otherwise."""
    if gst_type is None:
        return ZERO, ZERO, ZERO
    if gst_type == GstType.INTRA_STATE:
        cgst = money(tax / 2)
        return cgst, tax - cgst, ZERO
    return ZERO, ZERO, tax


def supply_type(seller_state_code: str | None, buyer_state: str | None) -> GstType | None:
    """INTRA_STATE when seller and buyer share a state; INTER_STATE otherwise.

    None when the buyer's state is not known yet (e.g. a preview without an
    address). A seller with no state configured is treated as inter-state.
    """
    if buyer_state is None:
        return None
    buyer_code = state_code_for(buyer_state)
    if seller_state_code and buyer_code and seller_state_code == buyer_code:
        return GstType.INTRA_STATE
    return GstType.INTER_STATE


def compute_tax(
    lines: list[TaxableLine],
    *,
    discount: Decimal,
    charges: Decimal,
    default_rate: Decimal,
    active: bool,
    gst_type: GstType | None,
) -> TaxResult:
    """Tax for a basket: goods at their own rates, delivery/COD charges at the default rate."""
    discounts = _spread(discount, [line.amount for line in lines])
    discounted = [line.amount - share for line, share in zip(lines, discounts, strict=True)]
    taxables = [
        money(amount * 100 / (100 + line.rate)) if line.prices_include_tax and line.rate else amount
        for line, amount in zip(lines, discounted, strict=True)
    ]

    if not active:
        result = TaxResult(gst_type=gst_type, charges_taxable=charges)
        for line, share, taxable in zip(lines, discounts, taxables, strict=True):
            result.lines[line.key] = LineTax(
                share, taxable, ZERO, ZERO, ZERO, ZERO, ZERO, line.hsn_code
            )
        return result

    # Group by rate so a single-rate basket rounds exactly like before.
    groups: dict[Decimal, list[tuple[object, Decimal]]] = {}
    for line, taxable in zip(lines, taxables, strict=True):
        groups.setdefault(line.rate, []).append((line.key, taxable))
    if charges > ZERO or not groups:
        groups.setdefault(default_rate, []).append(("__charges__", charges))

    result = TaxResult(gst_type=gst_type, charges_taxable=charges, charges_rate=default_rate)
    line_tax: dict[object, Decimal] = {}
    for rate, members in groups.items():
        group_taxable = sum((amount for _key, amount in members), ZERO)
        # Inclusive lines are extracted individually so mixed-rate/discount rounding is stable.
        group_tax = money(group_taxable * rate / PERCENT)
        for (key, _amount), share in zip(
            members, _spread(group_tax, [amount for _key, amount in members]), strict=True
        ):
            line_tax[key] = share

    by_key = {line.key: line for line in lines}
    for line, share, taxable in zip(lines, discounts, taxables, strict=True):
        tax = (
            money((line.amount - share) - taxable)
            if line.prices_include_tax
            else line_tax[line.key]
        )
        if line.prices_include_tax:
            result.included_tax += tax
        cgst, sgst, igst = split_tax(tax, gst_type)
        result.lines[line.key] = LineTax(
            share, taxable, by_key[line.key].rate, tax, cgst, sgst, igst, line.hsn_code
        )
        result.cgst += cgst
        result.sgst += sgst
        result.igst += igst

    result.charges_tax = line_tax.get("__charges__", ZERO)
    cgst, sgst, igst = split_tax(result.charges_tax, gst_type)
    result.cgst += cgst
    result.sgst += sgst
    result.igst += igst
    result.tax_amount = (
        sum((line_tax.get(line.key, ZERO) for line in lines), ZERO) + result.charges_tax
    )
    return result
