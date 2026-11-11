from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.addresses.schemas import AddressCreate
from app.auth.schemas import NormalizedPhone
from app.cod.schemas import CodAvailability
from app.core.pagination import PageParams
from app.core.schemas import PartialUpdate, StrictModel, not_blank
from app.orders.constants import (
    MAX_COURIER_NAME_LENGTH,
    MAX_TRACKING_DESCRIPTION_LENGTH,
    MAX_TRACKING_LOCATION_LENGTH,
    MAX_TRACKING_NUMBER_LENGTH,
    MAX_TRACKING_URL_LENGTH,
    GstType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    TrackingSource,
)
from app.payments.schemas import PaymentRead
from app.pricing.constants import PINCODE_PATTERN
from app.shipments.schemas import CustomerShipmentRead


class CheckoutItem(BaseModel):
    """One validated line, priced from the database."""

    product_id: UUID
    variant_id: UUID
    product_name: str
    variant_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    compare_at_price: Decimal | None = Field(
        default=None, description="Regular price when the unit price is a sale price"
    )
    hsn_code: str | None = None
    tax_configuration_id: UUID | None = None
    gst_rate: Decimal | None = None
    discount_amount: Decimal = Decimal("0.00")
    taxable_amount: Decimal | None = None
    tax_amount: Decimal = Decimal("0.00")
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")
    # Which rule set the rate and how sure the store is of it: frozen onto the
    # order line, but kept out of the shopper-facing preview.
    tax_rule_id: UUID | None = Field(default=None, exclude=True)
    tax_rule_code: str | None = Field(default=None, exclude=True)
    tax_source: str | None = Field(default=None, exclude=True)
    tax_verification: str | None = Field(default=None, exclude=True)


class GstBreakdown(BaseModel):
    """How tax_amount splits: CGST + SGST within the seller's state, else IGST."""

    gst_type: GstType | None
    place_of_supply: str | None = None
    cgst_amount: Decimal = Decimal("0.00")
    sgst_amount: Decimal = Decimal("0.00")
    igst_amount: Decimal = Decimal("0.00")


class DeliveryEstimate(BaseModel):
    pincode: str
    serviceable: bool
    min_delivery_days: int | None = None
    max_delivery_days: int | None = None
    earliest_delivery_date: date | None = None
    estimated_delivery_date: date | None = None


class CheckoutPreview(BaseModel):
    items: list[CheckoutItem]
    subtotal: Decimal
    coupon_code: str | None = None
    discount_amount: Decimal = Decimal("0.00")
    is_automatic_discount: bool = Field(
        default=False, description="The discount was applied without a code"
    )
    shipping_amount: Decimal
    shipping_discount: Decimal = Field(
        default=Decimal("0.00"), description="Delivery charge waived by a free-shipping offer"
    )
    cod_fee: Decimal = Decimal("0.00")
    tax_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal = Field(
        default=Decimal("0.00"), description="COD advance to pay before the order is confirmed"
    )
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY
    gst: GstBreakdown | None = None
    delivery: DeliveryEstimate | None = None
    cod: CodAvailability | None = None


class CheckoutCreate(StrictModel):
    """Which address to deliver to, and an optional coupon code -- the only
    things checkout accepts from the client. Everything priced (subtotal,
    discount, shipping, tax, total) is always computed server-side from the
    cart and coupon rules, never trusted from the request."""

    address_id: UUID
    coupon_code: str | None = Field(default=None, min_length=1, max_length=50)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY


class CheckoutPreviewCreate(StrictModel):
    """An optional address to price the cart against, validated when it is sent."""

    address_id: UUID | None = None
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY


class GuestContact(StrictModel):
    """Who is buying. The phone links the order to a customer record (made if new)."""

    name: str = Field(min_length=1, max_length=150)
    phone: NormalizedPhone
    email: EmailStr | None = None

    _strip = field_validator("name")(not_blank)


class GuestCheckoutCreate(StrictModel):
    contact: GuestContact
    address: AddressCreate
    coupon_code: str | None = Field(default=None, min_length=1, max_length=50)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY


class GuestCheckoutPreviewCreate(StrictModel):
    """Price a guest cart; an address (or just a pincode) adds delivery, GST and COD."""

    address: AddressCreate | None = None
    pincode: str | None = Field(default=None, pattern=PINCODE_PATTERN)
    phone: NormalizedPhone | None = None
    coupon_code: str | None = Field(default=None, min_length=1, max_length=50)
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY


class DeliveryAddressRead(BaseModel):
    full_name: str
    phone: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str


class OrderItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    variant_id: UUID
    product_name: str
    variant_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    hsn_code: str | None = None
    tax_configuration_id: UUID | None = None
    gst_rate: Decimal | None = None
    discount_amount: Decimal | None = None
    taxable_amount: Decimal | None = None
    tax_amount: Decimal | None = None
    cgst_amount: Decimal | None = None
    sgst_amount: Decimal | None = None
    igst_amount: Decimal | None = None
    tax_rule_code: str | None = None
    tax_source: str | None = None
    tax_verification: str | None = None


class ShipmentRead(BaseModel):
    courier_name: str | None = None
    tracking_number: str | None = None
    tracking_url: str | None = None


class OrderRead(BaseModel):
    id: UUID
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus
    items: list[OrderItemRead]
    subtotal: Decimal
    coupon_code: str | None = None
    discount_amount: Decimal = Decimal("0.00")
    shipping_amount: Decimal
    cod_fee: Decimal = Decimal("0.00")
    tax_amount: Decimal
    total_amount: Decimal
    advance_amount: Decimal = Decimal("0.00")
    currency: str
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY
    can_cancel: bool
    payment: PaymentRead | None
    payments: list[PaymentRead] = []
    gst: GstBreakdown | None = None
    prices_include_gst: bool = False
    tax_review_required: bool = False
    delivery_address: DeliveryAddressRead
    contact_email: str | None = None
    is_guest: bool = False
    estimated_delivery_date: date | None = None
    shipment: ShipmentRead = ShipmentRead()
    return_reason: str | None = None
    return_note: str | None = None
    created_at: datetime


class OrderSummaryRead(BaseModel):
    """A row in a list of orders -- no items, so listing stays cheap to read."""

    id: UUID
    order_number: str
    status: OrderStatus
    payment_status: PaymentStatus
    total_amount: Decimal
    currency: str
    payment_method: PaymentMethod = PaymentMethod.CASH_ON_DELIVERY
    tracking_number: str | None = None
    created_at: datetime


class ShipmentFields(StrictModel):
    courier_name: str | None = Field(default=None, max_length=MAX_COURIER_NAME_LENGTH)
    tracking_number: str | None = Field(default=None, max_length=MAX_TRACKING_NUMBER_LENGTH)
    tracking_url: str | None = Field(default=None, max_length=MAX_TRACKING_URL_LENGTH)


class OrderStatusUpdate(ShipmentFields):
    """Move an order on; shipment details may ride along (e.g. when marking SHIPPED)."""

    status: OrderStatus
    note: str | None = Field(default=None, max_length=MAX_TRACKING_DESCRIPTION_LENGTH)
    return_reason_id: UUID | None = Field(
        default=None, description="Only with status RETURNED: one of /admin/return-reasons"
    )
    return_note: str | None = Field(default=None, max_length=500)


class ShipmentUpdate(PartialUpdate, ShipmentFields):
    pass


class TrackingEventCreate(StrictModel):
    """A courier scan or note, e.g. "Arrived at Kochi hub"."""

    description: str = Field(min_length=1, max_length=MAX_TRACKING_DESCRIPTION_LENGTH)
    location: str | None = Field(default=None, max_length=MAX_TRACKING_LOCATION_LENGTH)
    occurred_at: datetime | None = None


class TrackingEventRead(BaseModel):
    status: OrderStatus | None
    description: str
    location: str | None
    source: TrackingSource
    occurred_at: datetime


class OrderTrackingRead(BaseModel):
    order_number: str
    status: OrderStatus
    estimated_delivery_date: date | None
    shipment: ShipmentRead
    events: list[TrackingEventRead]
    courier: CustomerShipmentRead | None = Field(
        default=None, description="Live courier status from the shipping provider, if booked"
    )


class PublicTrackingQuery(StrictModel):
    order_number: str = Field(min_length=1, max_length=32)
    phone: NormalizedPhone


class BulkLabelRequest(StrictModel):
    order_ids: list[UUID] = Field(min_length=1, max_length=100)


class DeliveryAddressUpdate(StrictModel):
    """A corrected delivery address for an order that has not shipped yet."""

    full_name: str = Field(min_length=1, max_length=150)
    phone: NormalizedPhone
    address_line_1: str = Field(min_length=1, max_length=255)
    address_line_2: str | None = Field(default=None, max_length=255)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    postal_code: str = Field(min_length=3, max_length=20)
    country: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=200)


class InvoiceParty(BaseModel):
    name: str | None
    gstin: str | None = None
    address: str | None
    state: str | None
    state_code: str | None


class InvoiceLine(BaseModel):
    description: str
    sku: str | None = None
    hsn_code: str | None
    quantity: int
    unit_price: Decimal
    discount: Decimal
    taxable_value: Decimal
    gst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    total: Decimal


class InvoiceTotals(BaseModel):
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    cod_fee: Decimal
    taxable_value: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    tax_amount: Decimal
    total: Decimal


class InvoiceRead(BaseModel):
    """GST tax invoice data; the frontend renders/prints it."""

    invoice_number: str
    invoice_date: date
    order_number: str
    order_status: OrderStatus
    gst_type: GstType | None
    tax_split_known: bool
    place_of_supply: str | None
    seller: InvoiceParty
    buyer: InvoiceParty
    lines: list[InvoiceLine]
    totals: InvoiceTotals
    currency: str


class OrderQuery(PageParams):
    """Filters the admin order listing accepts."""

    order_number: str | None = Field(default=None, max_length=32)
    status: OrderStatus | None = None
    payment_status: PaymentStatus | None = None
    search: str | None = Field(
        default=None,
        max_length=100,
        description="Order number, customer name/phone/email, delivery name/phone, product or SKU",
    )
    payment_method: PaymentMethod | None = None
    start_date: date | None = None
    end_date: date | None = None
