"""Round Decimal amounts to the scale the database stores, Numeric(12, 2)."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.catalogue.constants import PRICE_PRECISION, PRICE_SCALE

MONEY = Decimal("0.01")

ZERO = Decimal("0.00")

MAX_MONEY = Decimal(10) ** (PRICE_PRECISION - PRICE_SCALE) - Decimal("0.01")

def money(amount: Decimal) -> Decimal:
    """Round to paise, half up -- the way an amount is rounded on a receipt."""
    return amount.quantize(MONEY, rounding=ROUND_HALF_UP)
