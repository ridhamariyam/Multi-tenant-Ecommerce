"""The boundary between order fulfilment and a courier provider.

The service talks to a `ShippingProviderClient`; only app/shipments/shiprocket.py
knows Shiprocket's endpoints and field names. Adding another provider means
another implementation of this protocol, not changes to checkout or orders.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Protocol


class ShippingProviderError(Exception):
    """A provider call that did not succeed.

    `ambiguous`: the provider may have acted anyway (a timeout or server error
    on a call that books something), so look the result up before retrying.
    `retryable`: trying again later may work (rate limit, outage).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retryable: bool = False,
        ambiguous: bool = False,
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.ambiguous = ambiguous
        self.details = details


class ProviderNotConfiguredError(ShippingProviderError):
    """Credentials are missing, so no call was made."""


@dataclass(frozen=True)
class Package:
    weight_kg: Decimal
    length_cm: Decimal
    breadth_cm: Decimal
    height_cm: Decimal


@dataclass(frozen=True)
class RateQuery:
    pickup_postcode: str
    delivery_postcode: str
    package: Package
    cod: bool
    declared_value: Decimal


@dataclass(frozen=True)
class CourierRate:
    courier_id: str
    courier_name: str
    freight_charge: Decimal | None
    cod_charge: Decimal | None
    total_charge: Decimal | None
    cod_available: bool
    etd: str | None
    estimated_delivery_days: str | None
    is_recommended: bool = False


@dataclass(frozen=True)
class BookingItem:
    name: str
    sku: str
    units: int
    selling_price: Decimal
    discount: Decimal
    tax_rate: Decimal | None
    hsn: str | None


@dataclass(frozen=True)
class BookingRequest:
    channel_order_id: str
    order_date: datetime
    pickup_location: str
    customer_name: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postcode: str
    country: str
    email: str | None
    phone: str
    items: list[BookingItem]
    cod: bool
    shipping_charges: Decimal
    transaction_charges: Decimal
    total_discount: Decimal
    sub_total: Decimal
    package: Package


@dataclass(frozen=True)
class BookedOrder:
    provider_order_id: str
    provider_shipment_id: str | None
    awb_code: str | None = None
    courier_id: str | None = None
    courier_name: str | None = None
    status: str | None = None

    @property
    def is_cancelled(self) -> bool:
        return (self.status or "").upper() in {"CANCELED", "CANCELLED"}


@dataclass(frozen=True)
class AwbAssignment:
    awb_code: str
    courier_id: str | None
    courier_name: str | None
    applied_weight_kg: Decimal | None
    pickup_scheduled_date: str | None


@dataclass(frozen=True)
class PickupResult:
    scheduled_date: str | None
    token_number: str | None


@dataclass(frozen=True)
class TrackingScan:
    occurred_at: datetime
    status_code: int | None
    status_label: str | None
    courier_status: str | None
    activity: str | None
    location: str | None
    raw: dict[str, Any]


@dataclass(frozen=True)
class TrackingUpdate:
    """Tracking as the provider reports it: the current status and the scans behind it."""

    awb_code: str | None
    status_code: int | None
    status_label: str | None
    occurred_at: datetime | None
    etd: str | None
    track_url: str | None
    courier_name: str | None
    scans: list[TrackingScan] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PickupLocation:
    name: str
    postcode: str | None
    city: str | None
    state: str | None
    is_primary: bool


class ShippingProviderClient(Protocol):
    """What fulfilment needs from a courier provider. Every method raises
    `ShippingProviderError` on failure and never returns a guessed result."""

    async def check_rates(self, query: RateQuery) -> list[CourierRate]: ...

    async def create_order(self, booking: BookingRequest) -> BookedOrder: ...

    async def find_order(self, channel_order_id: str) -> BookedOrder | None: ...

    async def get_order(self, provider_order_id: str) -> BookedOrder | None: ...

    async def assign_awb(self, shipment_id: str, courier_id: str | None) -> AwbAssignment: ...

    async def schedule_pickup(self, shipment_id: str, pickup_date: date | None) -> PickupResult: ...

    async def generate_label(self, shipment_id: str) -> str: ...

    async def generate_manifest(self, shipment_id: str, provider_order_id: str) -> str: ...

    async def track(self, awb_code: str) -> TrackingUpdate: ...

    async def cancel_order(self, provider_order_id: str) -> None: ...

    async def pickup_locations(self) -> list[PickupLocation]: ...
