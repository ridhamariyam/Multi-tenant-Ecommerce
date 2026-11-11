from enum import Enum


class OrderStatus(str, Enum):
    """Where the order is in fulfilment. Separate from how it was paid."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    PROCESSING = "PROCESSING"
    PACKED = "PACKED"
    SHIPPED = "SHIPPED"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURNED = "RETURNED"
    REFUNDED = "REFUNDED"


class PaymentStatus(str, Enum):
    """Where the money is. Cash on delivery, so it lands on delivery."""

    PENDING = "PENDING"
    # A COD order whose advance has been paid; the balance is still due.
    PARTIALLY_PAID = "PARTIALLY_PAID"
    PAID = "PAID"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"


class PaymentMethod(str, Enum):
    """What the shopper chose at checkout; everything but cash is paid through Razorpay."""

    UPI = "UPI"
    CREDIT_CARD = "CREDIT_CARD"
    DEBIT_CARD = "DEBIT_CARD"
    NET_BANKING = "NET_BANKING"
    CASH_ON_DELIVERY = "CASH_ON_DELIVERY"


class GstType(str, Enum):
    """Intra-state supplies split GST into CGST + SGST; inter-state ones charge IGST."""

    INTRA_STATE = "INTRA_STATE"
    INTER_STATE = "INTER_STATE"


class TrackingSource(str, Enum):
    SYSTEM = "SYSTEM"
    ADMIN = "ADMIN"
    COURIER = "COURIER"


# The original flow is untouched (every old move is still allowed); PACKED and
# OUT_FOR_DELIVERY are optional extra stops, and RETURNED closes an undelivered
# shipment.
ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PENDING: frozenset(
        {OrderStatus.CONFIRMED, OrderStatus.PROCESSING, OrderStatus.CANCELLED}
    ),
    OrderStatus.CONFIRMED: frozenset(
        {OrderStatus.PROCESSING, OrderStatus.PACKED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PROCESSING: frozenset(
        {OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.CANCELLED}
    ),
    OrderStatus.PACKED: frozenset(
        {
            OrderStatus.SHIPPED,
            OrderStatus.OUT_FOR_DELIVERY,
            OrderStatus.DELIVERED,
            OrderStatus.CANCELLED,
        }
    ),
    OrderStatus.SHIPPED: frozenset(
        {OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED, OrderStatus.RETURNED}
    ),
    OrderStatus.OUT_FOR_DELIVERY: frozenset({OrderStatus.DELIVERED, OrderStatus.RETURNED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
    OrderStatus.RETURNED: frozenset(),
}

# Statuses that need the COD advance to have been paid first.
NEEDS_ADVANCE_PAID = frozenset(
    {
        OrderStatus.CONFIRMED,
        OrderStatus.PROCESSING,
        OrderStatus.PACKED,
        OrderStatus.SHIPPED,
        OrderStatus.OUT_FOR_DELIVERY,
        OrderStatus.DELIVERED,
    }
)

# Statuses that count as a sale on dashboards (ordered, not cancelled/returned).
FULFILMENT_STATUSES = (
    OrderStatus.PROCESSING,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
    OrderStatus.DELIVERED,
)

MAX_TRACKING_NUMBER_LENGTH = 100
MAX_COURIER_NAME_LENGTH = 100
MAX_TRACKING_URL_LENGTH = 500
MAX_TRACKING_DESCRIPTION_LENGTH = 255
MAX_TRACKING_LOCATION_LENGTH = 150
INVOICE_PREFIX_DEFAULT = "INV-"

CUSTOMER_CANCELLABLE_STATUSES = frozenset({OrderStatus.PENDING, OrderStatus.CONFIRMED})

MAX_ORDER_NUMBER_LENGTH = 32
MAX_IDEMPOTENCY_KEY_LENGTH = 80
ORDER_NUMBER_PREFIX = "ORD-"

ORDER_NUMBER_START = 100001
