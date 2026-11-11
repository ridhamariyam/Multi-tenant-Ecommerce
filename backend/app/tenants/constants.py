from enum import Enum

CURRENCY_CODE_LENGTH = 3

DEFAULT_CURRENCY = "INR"


class BrandStatus(str, Enum):
    """Platform-level standing of a brand, set by platform administrators."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


BRAND_STATUSES = tuple(s.value for s in BrandStatus)
