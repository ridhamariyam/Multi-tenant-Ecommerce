from enum import Enum


class PaymentStatus(str, Enum):
    """Where one payment attempt got to."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    EXPIRED = "EXPIRED"


class PaymentProvider(str, Enum):
    """How the money arrives."""

    COD = "COD"
    PREPAID = "PREPAID"
    RAZORPAY = "RAZORPAY"


class PaymentPurpose(str, Enum):
    FULL = "FULL"
    ADVANCE = "ADVANCE"
    BALANCE = "BALANCE"
