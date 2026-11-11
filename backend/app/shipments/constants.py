"""Shipment states, and how a courier provider's statuses map onto them."""

from __future__ import annotations

from enum import Enum


class ShipmentState(str, Enum):
    """Where a parcel is. Moved only by verified provider responses and tracking events."""

    # The record exists here; nothing has been booked with the provider yet.
    PENDING_FULFILMENT = "PENDING_FULFILMENT"
    # The provider holds an order and shipment for it, without a courier/AWB.
    SHIPMENT_CREATED = "SHIPMENT_CREATED"
    # A courier is assigned and the AWB is known: a label can be printed.
    READY_TO_SHIP = "READY_TO_SHIP"
    PICKUP_SCHEDULED = "PICKUP_SCHEDULED"
    PICKED_UP = "PICKED_UP"
    IN_TRANSIT = "IN_TRANSIT"
    OUT_FOR_DELIVERY = "OUT_FOR_DELIVERY"
    DELIVERED = "DELIVERED"
    # Undelivered attempt, pickup failure, delay, lost or damaged parcel.
    DELIVERY_EXCEPTION = "DELIVERY_EXCEPTION"
    # Coming back to the seller (RTO initiated / in transit).
    RETURN_TO_ORIGIN = "RETURN_TO_ORIGIN"
    # Arrived back at the seller.
    RETURNED_TO_ORIGIN = "RETURNED_TO_ORIGIN"
    CANCELLED = "CANCELLED"


TERMINAL_STATES = frozenset(
    {ShipmentState.DELIVERED, ShipmentState.RETURNED_TO_ORIGIN, ShipmentState.CANCELLED}
)

# The forward journey. A tracking event may only move a parcel forward along
# it; DELIVERY_EXCEPTION sits beside IN_TRANSIT/OUT_FOR_DELIVERY (a failed
# attempt can be retried), and once a return has started only its arrival
# back can follow.
STATE_RANK: dict[ShipmentState, int] = {
    ShipmentState.PENDING_FULFILMENT: 0,
    ShipmentState.SHIPMENT_CREATED: 10,
    ShipmentState.READY_TO_SHIP: 20,
    ShipmentState.PICKUP_SCHEDULED: 30,
    ShipmentState.PICKED_UP: 40,
    ShipmentState.IN_TRANSIT: 50,
    ShipmentState.DELIVERY_EXCEPTION: 50,
    ShipmentState.OUT_FOR_DELIVERY: 60,
    ShipmentState.RETURN_TO_ORIGIN: 80,
    ShipmentState.DELIVERED: 100,
    ShipmentState.RETURNED_TO_ORIGIN: 100,
    ShipmentState.CANCELLED: 100,
}

# A shipment the courier has not collected yet; the provider allows
# cancelling it ("before the Out for Pickup state").
CANCELLABLE_STATES = frozenset(
    {
        ShipmentState.PENDING_FULFILMENT,
        ShipmentState.SHIPMENT_CREATED,
        ShipmentState.READY_TO_SHIP,
        ShipmentState.PICKUP_SCHEDULED,
    }
)

# States in which polling the provider for tracking is useful.
TRACKABLE_STATES = frozenset(
    {
        ShipmentState.READY_TO_SHIP,
        ShipmentState.PICKUP_SCHEDULED,
        ShipmentState.PICKED_UP,
        ShipmentState.IN_TRANSIT,
        ShipmentState.OUT_FOR_DELIVERY,
        ShipmentState.DELIVERY_EXCEPTION,
        ShipmentState.RETURN_TO_ORIGIN,
    }
)


class ShippingProvider(str, Enum):
    SHIPROCKET = "SHIPROCKET"


class ShipmentPaymentMode(str, Enum):
    """How the courier treats the parcel: collect cash at the door, or not."""

    COD = "COD"
    PREPAID = "PREPAID"


class ShipmentOperation(str, Enum):
    """A provider call that changes something, recorded so it can be retried safely."""

    CREATE = "CREATE"
    ASSIGN_AWB = "ASSIGN_AWB"
    SCHEDULE_PICKUP = "SCHEDULE_PICKUP"
    CANCEL = "CANCEL"


class OperationStatus(str, Enum):
    IN_PROGRESS = "IN_PROGRESS"
    # The provider refused it; nothing happened there. Safe to retry after fixing.
    FAILED = "FAILED"
    # The call timed out or the provider erred: it may or may not have happened.
    # Retrying first looks the result up at the provider before calling again.
    UNKNOWN = "UNKNOWN"


class ShipmentEventSource(str, Enum):
    WEBHOOK = "WEBHOOK"
    POLL = "POLL"
    API = "API"


# Shiprocket's shipment status codes, from "Cancel a Shipment" in
# https://apidocs.shiprocket.in/ (the documented status code table).
# Codes for international/fulfilment-centre flows this store does not use map to
# None: the event is still recorded, but it does not move the shipment.
SHIPROCKET_STATUS_STATES: dict[int, ShipmentState | None] = {
    1: ShipmentState.READY_TO_SHIP,  # AWB Assigned
    2: ShipmentState.READY_TO_SHIP,  # Label Generated
    3: ShipmentState.PICKUP_SCHEDULED,  # Pickup Scheduled/Generated
    4: ShipmentState.PICKUP_SCHEDULED,  # Pickup Queued
    5: ShipmentState.PICKUP_SCHEDULED,  # Manifest Generated
    6: ShipmentState.IN_TRANSIT,  # Shipped
    7: ShipmentState.DELIVERED,  # Delivered
    8: ShipmentState.CANCELLED,  # Cancelled
    9: ShipmentState.RETURN_TO_ORIGIN,  # RTO Initiated
    10: ShipmentState.RETURNED_TO_ORIGIN,  # RTO Delivered
    11: None,  # Pending
    12: ShipmentState.DELIVERY_EXCEPTION,  # Lost
    13: ShipmentState.DELIVERY_EXCEPTION,  # Pickup Error
    14: ShipmentState.RETURN_TO_ORIGIN,  # RTO Acknowledged
    15: ShipmentState.PICKUP_SCHEDULED,  # Pickup Rescheduled
    16: None,  # Cancellation Requested -- not cancelled until 8 arrives
    17: ShipmentState.OUT_FOR_DELIVERY,  # Out For Delivery
    18: ShipmentState.IN_TRANSIT,  # In Transit
    19: ShipmentState.PICKUP_SCHEDULED,  # Out For Pickup
    20: ShipmentState.DELIVERY_EXCEPTION,  # Pickup Exception
    21: ShipmentState.DELIVERY_EXCEPTION,  # Undelivered
    22: ShipmentState.DELIVERY_EXCEPTION,  # Delayed
    23: ShipmentState.DELIVERY_EXCEPTION,  # Partial_Delivered
    24: ShipmentState.DELIVERY_EXCEPTION,  # Destroyed
    25: ShipmentState.DELIVERY_EXCEPTION,  # Damaged
    26: None,  # Fulfilled
    38: ShipmentState.IN_TRANSIT,  # Reached at Destination
    39: ShipmentState.DELIVERY_EXCEPTION,  # Misrouted
    40: ShipmentState.RETURN_TO_ORIGIN,  # RTO NDR
    41: ShipmentState.RETURN_TO_ORIGIN,  # RTO OFD
    42: ShipmentState.PICKED_UP,  # Picked Up
    43: None,  # Self Fulfilled
    44: ShipmentState.DELIVERY_EXCEPTION,  # DISPOSED_OFF
    45: ShipmentState.CANCELLED,  # CANCELLED_BEFORE_DISPATCHED
    46: ShipmentState.RETURN_TO_ORIGIN,  # RTO_IN_TRANSIT
    47: ShipmentState.DELIVERY_EXCEPTION,  # QC Failed
    48: None,  # Reached Warehouse
    51: ShipmentState.PICKED_UP,  # Handover to Courier
    52: None,  # Shipment Booked
}

MAX_PROVIDER_ID_LENGTH = 64
MAX_AWB_LENGTH = 64
MAX_COURIER_NAME_LENGTH = 100
MAX_URL_LENGTH = 1000
MAX_STATUS_LABEL_LENGTH = 100
MAX_ERROR_LENGTH = 500
MAX_ACTIVITY_LENGTH = 500
MAX_LOCATION_LENGTH = 150
MAX_PICKUP_LOCATION_LENGTH = 100
MAX_DEDUPE_KEY_LENGTH = 200

# Parcel limits the provider accepts: dimensions over 0.5 cm, weight over 0 kg.
MIN_DIMENSION_CM = "0.5"
MAX_DIMENSION_CM = "300"
MAX_WEIGHT_KG = "100"

TOKEN_CACHE_PREFIX = "shiprocket:token"
