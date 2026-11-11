from enum import Enum


class BlacklistSource(str, Enum):
    """Who put a phone on the COD blacklist."""

    MANUAL = "MANUAL"
    # Added by the system after too many undelivered (RETURNED) COD orders.
    AUTO = "AUTO"


class CodUnavailableReason(str, Enum):
    DISABLED = "DISABLED"
    ORDER_TOO_LARGE = "ORDER_TOO_LARGE"
    ORDER_TOO_SMALL = "ORDER_TOO_SMALL"
    PINCODE_RESTRICTED = "PINCODE_RESTRICTED"
    PHONE_BLACKLISTED = "PHONE_BLACKLISTED"


MAX_REASON_LENGTH = 255
