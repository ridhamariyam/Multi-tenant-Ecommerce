from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from app.core.schemas import StrictModel, blank_to_none
from app.pricing.constants import PINCODE_PATTERN
from app.shipments.constants import (
    MAX_DIMENSION_CM,
    MAX_PICKUP_LOCATION_LENGTH,
    MAX_WEIGHT_KG,
    MIN_DIMENSION_CM,
    OperationStatus,
    ShipmentEventSource,
    ShipmentOperation,
    ShipmentPaymentMode,
    ShipmentState,
    ShippingProvider,
)

Weight = Field(gt=Decimal("0"), le=Decimal(MAX_WEIGHT_KG), max_digits=7, decimal_places=3)


def _dimension():
    return Field(
        gt=Decimal(MIN_DIMENSION_CM), le=Decimal(MAX_DIMENSION_CM), max_digits=6, decimal_places=1
    )


class PackageInput(StrictModel):
    """The packed parcel as weighed and measured: kg and cm."""

    weight_kg: Decimal = Weight
    length_cm: Decimal = _dimension()
    breadth_cm: Decimal = _dimension()
    height_cm: Decimal = _dimension()


class ShipmentCreate(StrictModel):
    package: PackageInput | None = Field(
        default=None, description="Leave out to use the configured package defaults"
    )
    courier_id: str | None = Field(
        default=None,
        max_length=20,
        description="Also assign this courier (from the rates list) right after booking",
    )


class AwbAssign(StrictModel):
    courier_id: str | None = Field(
        default=None, max_length=20, description="Leave out for the provider's default courier"
    )


class PickupCreate(StrictModel):
    pickup_date: date | None = Field(default=None, description="Leave out for the next slot")


class RateQueryParams(StrictModel):
    weight_kg: Decimal | None = Field(
        default=None, gt=Decimal("0"), le=Decimal(MAX_WEIGHT_KG), decimal_places=3
    )
    length_cm: Decimal | None = Field(
        default=None, gt=Decimal(MIN_DIMENSION_CM), le=Decimal(MAX_DIMENSION_CM)
    )
    breadth_cm: Decimal | None = Field(
        default=None, gt=Decimal(MIN_DIMENSION_CM), le=Decimal(MAX_DIMENSION_CM)
    )
    height_cm: Decimal | None = Field(
        default=None, gt=Decimal(MIN_DIMENSION_CM), le=Decimal(MAX_DIMENSION_CM)
    )

    def package(self) -> PackageInput | None:
        values = (self.weight_kg, self.length_cm, self.breadth_cm, self.height_cm)
        if all(value is None for value in values):
            return None
        if any(value is None for value in values):
            raise ValueError("Give weight, length, breadth and height together")
        return PackageInput(
            weight_kg=self.weight_kg,
            length_cm=self.length_cm,
            breadth_cm=self.breadth_cm,
            height_cm=self.height_cm,
        )


class CourierRateRead(BaseModel):
    courier_id: str
    courier_name: str
    freight_charge: Decimal | None
    cod_charge: Decimal | None
    total_charge: Decimal | None = Field(
        description="Provider's quoted rate; additional taxes or fees may apply"
    )
    cod_available: bool
    etd: str | None = Field(description="The provider's delivery estimate, as given")
    estimated_delivery_days: str | None
    is_recommended: bool


class CourierRatesRead(BaseModel):
    pickup_postcode: str
    delivery_postcode: str
    payment_mode: ShipmentPaymentMode
    package: PackageInput
    declared_value: Decimal
    couriers: list[CourierRateRead]


class ShipmentEventRead(BaseModel):
    source: ShipmentEventSource
    provider_status_code: int | None
    courier_status: str | None
    status_label: str | None
    state: ShipmentState | None
    activity: str | None
    location: str | None
    occurred_at: datetime


class ShipmentRead(BaseModel):
    id: UUID
    order_id: UUID
    provider: ShippingProvider
    attempt: int
    channel_order_id: str
    state: ShipmentState
    provider_order_id: str | None
    provider_shipment_id: str | None
    awb_code: str | None
    courier_company_id: str | None
    courier_name: str | None
    tracking_url: str | None
    label_url: str | None
    manifest_url: str | None
    pickup_location: str
    pickup_scheduled_date: str | None
    pickup_token_number: str | None
    provider_etd: str | None
    package: PackageInput
    applied_weight_kg: Decimal | None
    payment_mode: ShipmentPaymentMode
    declared_value: Decimal
    cod_amount: Decimal = Field(description="Cash the courier collects at the door")
    freight_charge: Decimal | None = Field(description="Courier freight quoted to the store")
    cod_charge: Decimal | None = Field(description="Courier COD handling quoted to the store")
    provider_status_code: int | None
    provider_status_label: str | None
    last_event_at: datetime | None
    pending_operation: ShipmentOperation | None
    operation_status: OperationStatus | None
    last_error: str | None
    last_error_at: datetime | None
    retry_count: int
    last_synced_at: datetime | None
    picked_up_at: datetime | None
    delivered_at: datetime | None
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    actions: list[str] = Field(description="What can be done next: create_awb, pickup, ...")
    recovery_hint: str | None = None
    events: list[ShipmentEventRead] = []


class OrderShipmentsRead(BaseModel):
    """An order's current shipment, earlier cancelled attempts, and whether booking is possible."""

    provider: ShippingProvider
    provider_enabled: bool
    credentials_configured: bool
    can_create: bool
    create_blocked_reason: str | None
    package_defaults: PackageInput | None
    current: ShipmentRead | None
    history: list[ShipmentRead]


class ProviderSettingsRead(BaseModel):
    provider: ShippingProvider
    is_enabled: bool
    credentials_configured: bool
    webhook_configured: bool
    pickup_location: str | None
    pickup_postcode: str | None
    fallback_email: str | None
    package_defaults: PackageInput | None
    updated_at: datetime | None


class ProviderSettingsUpdate(StrictModel):
    is_enabled: bool = Field(
        description="Allow booking real shipments. Needs a pickup location and credentials."
    )
    pickup_location: str | None = Field(default=None, max_length=MAX_PICKUP_LOCATION_LENGTH)
    pickup_postcode: str | None = Field(default=None, pattern=PINCODE_PATTERN)
    fallback_email: EmailStr | None = None
    package_defaults: PackageInput | None = None

    _blank = field_validator("pickup_location", mode="before")(blank_to_none)

    @model_validator(mode="after")
    def _enabled_needs_pickup(self) -> ProviderSettingsUpdate:
        if self.is_enabled and not (self.pickup_location and self.pickup_postcode):
            raise ValueError("Set the pickup location name and its pincode before enabling")
        return self


class PickupLocationRead(BaseModel):
    name: str
    postcode: str | None
    city: str | None
    state: str | None
    is_primary: bool


class CustomerShipmentRead(BaseModel):
    """What a shopper sees: official tracking only, no store costs or internals."""

    state: ShipmentState
    status_label: str | None
    courier_name: str | None
    awb_code: str | None
    tracking_url: str | None
    provider_etd: str | None = Field(description="The courier's estimate, as reported")
    last_event_at: datetime | None
