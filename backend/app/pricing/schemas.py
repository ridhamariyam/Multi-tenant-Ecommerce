from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.catalogue.constants import HSN_CODE_PATTERN, PRICE_SCALE
from app.core.money import MAX_MONEY
from app.core.pagination import PageParams
from app.core.schemas import StrictModel
from app.orders.constants import GstType
from app.pricing.constants import (
    DEFAULT_INVOICE_PREFIX,
    DEFAULT_MAX_DELIVERY_DAYS,
    DEFAULT_MIN_DELIVERY_DAYS,
    DEFAULT_TAX_CLASSIFICATION,
    GSTIN_PATTERN,
    MAX_DELIVERY_DAYS,
    MAX_TAX_PERCENTAGE,
    PINCODE_PATTERN,
)

Money = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=PRICE_SCALE)
DeliveryDays = Field(ge=0, le=MAX_DELIVERY_DAYS)


class ShippingSettingsUpdate(StrictModel):
    shipping_amount: Decimal = Field(ge=0, le=MAX_MONEY, decimal_places=PRICE_SCALE)
    free_shipping_minimum: Decimal | None = Field(
        default=None, ge=0, le=MAX_MONEY, decimal_places=PRICE_SCALE
    )
    is_active: bool = True
    min_delivery_days: int = Field(default=DEFAULT_MIN_DELIVERY_DAYS, ge=0, le=MAX_DELIVERY_DAYS)
    max_delivery_days: int = Field(default=DEFAULT_MAX_DELIVERY_DAYS, ge=0, le=MAX_DELIVERY_DAYS)
    restrict_to_listed_pincodes: bool = Field(
        default=False,
        description="Deliver only to pincodes listed as serviceable",
    )

    @model_validator(mode="after")
    def _days_ordered(self) -> ShippingSettingsUpdate:
        if self.max_delivery_days < self.min_delivery_days:
            raise ValueError("max_delivery_days must not be less than min_delivery_days")
        return self


class ShippingSettingsRead(BaseModel):
    shipping_amount: Decimal
    free_shipping_minimum: Decimal | None
    is_active: bool
    min_delivery_days: int = DEFAULT_MIN_DELIVERY_DAYS
    max_delivery_days: int = DEFAULT_MAX_DELIVERY_DAYS
    restrict_to_listed_pincodes: bool = False


class TaxSettingsUpdate(StrictModel):
    tax_percentage: Decimal = Field(ge=0, le=MAX_TAX_PERCENTAGE, decimal_places=2)
    is_active: bool = True


class TaxSettingsRead(BaseModel):
    tax_percentage: Decimal
    is_active: bool
    confirmed_by_ca: bool = False


# ---------------------------------------------------------------- pincodes


Pincode = Field(pattern=PINCODE_PATTERN, description="6-digit Indian pincode")


class PincodeRuleWrite(StrictModel):
    """Delivery rules for one pincode (PUT replaces them)."""

    is_serviceable: bool = True
    cod_available: bool = True
    min_delivery_days: int | None = Field(default=None, ge=0, le=MAX_DELIVERY_DAYS)
    max_delivery_days: int | None = Field(default=None, ge=0, le=MAX_DELIVERY_DAYS)
    shipping_amount: Decimal | None = Money
    city: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)

    @model_validator(mode="after")
    def _days_together(self) -> PincodeRuleWrite:
        if (self.min_delivery_days is None) != (self.max_delivery_days is None):
            raise ValueError("set both min_delivery_days and max_delivery_days, or neither")
        if (
            self.min_delivery_days is not None
            and self.max_delivery_days is not None
            and self.max_delivery_days < self.min_delivery_days
        ):
            raise ValueError("max_delivery_days must not be less than min_delivery_days")
        return self


class PincodeRuleBulkItem(PincodeRuleWrite):
    pincode: str = Pincode


class PincodeRuleBulk(StrictModel):
    rules: list[PincodeRuleBulkItem] = Field(min_length=1, max_length=1000)

    @field_validator("rules")
    @classmethod
    def _unique(cls, value: list[PincodeRuleBulkItem]) -> list[PincodeRuleBulkItem]:
        codes = [rule.pincode for rule in value]
        if len(codes) != len(set(codes)):
            raise ValueError("each pincode may only appear once")
        return value


class PincodeRuleRead(BaseModel):
    pincode: str
    is_serviceable: bool
    cod_available: bool
    min_delivery_days: int | None
    max_delivery_days: int | None
    shipping_amount: Decimal | None
    city: str | None
    state: str | None


class PincodeQuery(PageParams):
    search: str | None = Field(default=None, max_length=6, description="Pincode prefix")
    is_serviceable: bool | None = None


class DeliveryCheckQuery(StrictModel):
    pincode: str = Pincode
    subtotal: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        le=MAX_MONEY,
        description="Basket value, so a free-shipping threshold can apply",
    )


class DeliveryCheckRead(BaseModel):
    """Everything the pincode box on the product or cart page shows."""

    pincode: str
    serviceable: bool
    message: str
    min_delivery_days: int | None = None
    max_delivery_days: int | None = None
    earliest_delivery_date: date | None = None
    estimated_delivery_date: date | None = None
    shipping_amount: Decimal | None = None
    free_shipping_minimum: Decimal | None = None
    cod_available: bool = False
    currency: str


# ---------------------------------------------------------------- GST


class GstSettingsUpdate(StrictModel):
    gstin: str | None = Field(default=None, pattern=GSTIN_PATTERN)
    legal_name: str | None = Field(default=None, max_length=200)
    address: str | None = Field(default=None, max_length=500)
    state: str | None = Field(
        default=None, max_length=100, description="Seller state name or 2-digit GST code"
    )
    invoice_prefix: str = Field(default=DEFAULT_INVOICE_PREFIX, min_length=1, max_length=20)
    shipping_sac_code: str | None = Field(default=None, pattern=HSN_CODE_PATTERN)
    registration_status: Literal[
        "REGISTERED", "NOT_REGISTERED", "APPLICATION_PENDING", "UNKNOWN"
    ] = "UNKNOWN"
    accounting_software: Literal["TALLY", "ZOHO_BOOKS", "OTHER", "NONE", "NOT_DECIDED"] = (
        "NOT_DECIDED"
    )
    configuration_status: Literal["DRAFT", "PENDING_CA_CONFIRMATION", "ACTIVE"] = "DRAFT"
    prices_include_gst: bool = False
    gst_enabled: bool = True
    default_classification: Literal["APPAREL"] | None = Field(
        default=DEFAULT_TAX_CLASSIFICATION,
        description="Classification assumed for products without an HSN code; null assumes none",
    )
    fallback_gst_rate: Decimal | None = Field(
        default=None, ge=0, le=MAX_TAX_PERCENTAGE, decimal_places=2,
        description="Rate for unclassified products; null keeps the system fallback",
    )

    @field_validator("gstin")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class GstSettingsRead(BaseModel):
    gstin: str | None = None
    legal_name: str | None = None
    address: str | None = None
    state: str | None = None
    state_code: str | None = None
    invoice_prefix: str = DEFAULT_INVOICE_PREFIX
    shipping_sac_code: str | None = None
    registration_status: str = "UNKNOWN"
    accounting_software: str = "NOT_DECIDED"
    configuration_status: str = "DRAFT"
    prices_include_gst: bool = False
    gst_enabled: bool = True
    default_classification: str | None = DEFAULT_TAX_CLASSIFICATION
    fallback_gst_rate: Decimal | None = None
    defaults_reviewed_at: datetime | None = None
    defaults_reviewed_by_id: UUID | None = None
    # True when the settings row does not exist yet and platform defaults apply.
    is_system_default: bool = False
    updated_at: datetime | None = None
    updated_by_id: UUID | None = None
    confirmed_at: datetime | None = None
    confirmed_by_id: UUID | None = None


class GstDefaultRuleRead(BaseModel):
    id: UUID
    code: str
    classification: str
    description: str
    hsn_prefixes: list[str]
    min_unit_value: Decimal | None
    max_unit_value: Decimal | None
    gst_rate: Decimal
    effective_from: date
    effective_to: date | None
    is_fallback: bool
    verification_status: str
    source: str | None
    in_force: bool = False


class GstDefaultsRead(BaseModel):
    """The system rules, and this tenant's review of them."""

    rules: list[GstDefaultRuleRead]
    default_classification: str | None
    fallback_gst_rate: Decimal | None
    system_fallback_rate: Decimal | None
    reviewed_at: datetime | None = None
    reviewed_by_id: UUID | None = None
    status: Literal["AWAITING_VERIFICATION", "REVIEWED"]


class GstDefaultsReview(StrictModel):
    reviewed: bool = Field(description="The store has checked the default rules apply to it")


class ProductTaxReviewRead(BaseModel):
    """How one product's variants are taxed today, and whether that needs a look."""

    product_id: UUID
    product_name: str
    category_name: str | None = None
    hsn_code: str | None = None
    source: str
    verification: str
    rule_codes: list[str] = []
    rates: list[Decimal]
    reason: str
    needs_review: bool


class StorefrontTaxInfo(BaseModel):
    """What the storefront may say about tax -- no registration details."""

    gst_enabled: bool
    prices_include_gst: bool


class TaxRateConfigurationWrite(StrictModel):
    product_id: UUID | None = None
    category_id: UUID | None = None
    hsn_code: str = Field(pattern=HSN_CODE_PATTERN)
    gst_rate: Decimal = Field(ge=0, le=MAX_TAX_PERCENTAGE, decimal_places=2)
    effective_from: date
    ca_confirmed: bool = False

    @model_validator(mode="after")
    def _one_target(self) -> TaxRateConfigurationWrite:
        if (self.product_id is None) == (self.category_id is None):
            raise ValueError("select exactly one product or category")
        return self

    @field_validator("hsn_code")
    @classmethod
    def _hsn_digits(cls, value: str) -> str:
        value = value.strip()
        if not value.isdigit():
            raise ValueError("HSN code must contain only digits")
        return value


class TaxRateConfigurationRead(BaseModel):
    id: UUID
    product_id: UUID | None
    category_id: UUID | None
    product_name: str | None = None
    category_name: str | None = None
    hsn_code: str
    gst_rate: Decimal
    effective_from: date
    status: str
    ca_confirmed: bool
    approved_at: datetime | None = None
    created_by_id: UUID | None = None
    approved_by_id: UUID | None = None
    created_at: datetime


class TaxRateTargetRead(BaseModel):
    id: UUID
    name: str


class TaxRateTargetsRead(BaseModel):
    products: list[TaxRateTargetRead]
    categories: list[TaxRateTargetRead]


class TaxRateApproval(StrictModel):
    ca_confirmed: bool = Field(description="Approval can proceed only after CA confirmation")


class GstReportQuery(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _ordered(self) -> GstReportQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class GstReportRow(BaseModel):
    component: Literal["ITEMS", "CHARGES_AND_ADJUSTMENTS"] = "ITEMS"
    gst_type: GstType | None
    gst_rate: Decimal | None
    hsn_code: str | None = None
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal


class GstReportRead(BaseModel):
    start_date: date
    end_date: date
    order_count: int
    taxable_amount: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal
    unclassified_tax_amount: Decimal = Decimal("0.00")
    tax_amount: Decimal
    by_rate: list[GstReportRow]
    currency: str
