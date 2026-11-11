from decimal import Decimal

PERCENT = Decimal("100")

MAX_TAX_PERCENTAGE = Decimal("100")

SEED_SHIPPING_AMOUNT = Decimal("100.00")
SEED_FREE_SHIPPING_MINIMUM = Decimal("2000.00")
SEED_TAX_PERCENTAGE = Decimal("18.00")

DEFAULT_MIN_DELIVERY_DAYS = 3
DEFAULT_MAX_DELIVERY_DAYS = 7
MAX_DELIVERY_DAYS = 60

PINCODE_PATTERN = r"^[1-9][0-9]{5}$"
GSTIN_PATTERN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
STATE_CODE_PATTERN = r"^[0-9]{2}$"
DEFAULT_INVOICE_PREFIX = "INV-"
# SAC 9968: postal and courier services -- how delivery charges are classified.
DEFAULT_SHIPPING_SAC_CODE = "996812"

# GST dates are Indian dates: a rate change at midnight IST applies from then.
GST_TIMEZONE = "Asia/Kolkata"


class TaxClassification:
    """What a system default rule covers. A product is classified by its HSN code,
    or else by the store's assumed classification (GstSettings.default_classification)."""

    APPAREL = "APPAREL"
    FALLBACK = "FALLBACK"

    ASSUMABLE = (APPAREL,)


class TaxSource:
    """Where a line's GST rate came from, strongest first."""

    APPROVED_OVERRIDE = "APPROVED_OVERRIDE"  # an ACTIVE, CA-confirmed TaxRateConfiguration
    MANUAL = "MANUAL"  # gst_rate typed on the product or its category
    SYSTEM_DEFAULT = "SYSTEM_DEFAULT"  # a GstDefaultRule matched by classification
    FALLBACK = "FALLBACK"  # nothing classified the product
    DISABLED = "DISABLED"  # the store charges no GST


class TaxVerification:
    VERIFIED = "VERIFIED"
    AWAITING_VERIFICATION = "AWAITING_VERIFICATION"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    NOT_APPLICABLE = "NOT_APPLICABLE"


RULE_UNVERIFIED = "UNVERIFIED"
RULE_VERIFIED = "VERIFIED"

DEFAULT_TAX_CLASSIFICATION = TaxClassification.APPAREL
