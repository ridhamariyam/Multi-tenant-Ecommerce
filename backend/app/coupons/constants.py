from __future__ import annotations

from enum import Enum


class DiscountType(str, Enum):
    FIXED_AMOUNT = "FIXED_AMOUNT"
    PERCENTAGE = "PERCENTAGE"
    # Removes the delivery charge; discount_value is unused.
    FREE_SHIPPING = "FREE_SHIPPING"
    # Buy `buy_quantity`, get `get_quantity` of the cheaper eligible units at
    # `discount_value` percent off (100 = free).
    BOGO = "BOGO"


# Types whose discount_value is a percentage, so it may not exceed 100.
PERCENT_TYPES = frozenset({DiscountType.PERCENTAGE, DiscountType.BOGO})

MAX_COUPON_CATEGORIES = 50
