from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.catalogue.constants import PRICE_SCALE
from app.core.money import MAX_MONEY
from app.core.pagination import PageParams
from app.coupons.constants import MAX_COUPON_CATEGORIES, DiscountType


class CouponQuery(PageParams):
    """The admin listing filter, on top of the usual page controls."""

    active_only: bool = False


RULE_FIELDS_DOC = (
    "FREE_SHIPPING needs no discount_value. BOGO needs buy_quantity and "
    "get_quantity; its discount_value is the percent off the 'get' items (100 = free)."
)


def _clean_weekdays(value: list[int] | None) -> list[int] | None:
    if value is None:
        return None
    if any(day < 0 or day > 6 for day in value):
        raise ValueError("weekdays are 0 (Monday) to 6 (Sunday)")
    return sorted(set(value)) or None


class CouponCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    discount_type: DiscountType = Field(description=RULE_FIELDS_DOC)
    discount_value: Decimal | None = Field(
        default=None,
        gt=0,
        le=MAX_MONEY,
        decimal_places=PRICE_SCALE,
        )
    min_order_amount: Decimal | None = Field(
        default=None, 
        ge=0, 
        le=MAX_MONEY, 
        decimal_places=PRICE_SCALE,
        )
    max_discount_amount: Decimal | None = Field(
        default=None, 
        ge=0, 
        le=MAX_MONEY, 
        decimal_places=PRICE_SCALE,
        )
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=0)
    per_customer_usage_limit: int | None = Field(default=None, ge=0)
    is_active: bool = True
    is_automatic: bool = Field(
        default=False, description="Applied at checkout without a code"
    )
    first_order_only: bool = False
    min_quantity: int | None = Field(
        default=None, ge=1, le=1000, description="Volume rule: minimum eligible units"
    )
    buy_quantity: int | None = Field(default=None, ge=1, le=100)
    get_quantity: int | None = Field(default=None, ge=1, le=100)
    valid_weekdays: list[int] | None = Field(
        default=None,
        max_length=7,
        description="Days it works on, 0 = Monday ... 6 = Sunday (shop time). Empty = every day.",
    )

    _weekdays = field_validator("valid_weekdays")(_clean_weekdays)
    category_ids: list[UUID] | None = Field(
        default=None,
        max_length=MAX_COUPON_CATEGORIES,
        description="Only products in these categories (and sub-categories) are discounted",
    )

class CouponUpdate(BaseModel):
    discount_type: DiscountType | None = None
    discount_value: Decimal | None = Field(
        default=None, 
        gt=0, 
        le=MAX_MONEY, 
        decimal_places=PRICE_SCALE)
    min_order_amount: Decimal | None = Field(
        default=None, 
        ge=0, 
        le=MAX_MONEY, 
        decimal_places=PRICE_SCALE,
        )
    max_discount_amount: Decimal | None = Field(
        default=None, 
        ge=0, le=MAX_MONEY, 
        decimal_places=PRICE_SCALE,
        )
    starts_at: datetime | None = None
    expires_at: datetime | None = None
    usage_limit: int | None = Field(default=None, ge=0)
    per_customer_usage_limit: int | None = Field(default=None, ge=0)
    is_active: bool | None = None
    is_automatic: bool | None = Field(
        default=None, description="Applied at checkout without a code"
    )
    first_order_only: bool | None = None
    min_quantity: int | None = Field(
        default=None, ge=1, le=1000, description="Volume rule: minimum eligible units"
    )
    buy_quantity: int | None = Field(default=None, ge=1, le=100)
    get_quantity: int | None = Field(default=None, ge=1, le=100)
    valid_weekdays: list[int] | None = Field(
        default=None,
        max_length=7,
        description="Days it works on, 0 = Monday ... 6 = Sunday (shop time). Empty = every day.",
    )

    _weekdays = field_validator("valid_weekdays")(_clean_weekdays)
    category_ids: list[UUID] | None = Field(
        default=None,
        max_length=MAX_COUPON_CATEGORIES,
        description="Only products in these categories (and sub-categories) are discounted",
    )

class CouponRead(BaseModel):
    id: UUID
    code: str
    discount_type: DiscountType
    discount_value: Decimal
    currency: str
    min_order_amount: Decimal | None
    max_discount_amount: Decimal | None
    starts_at: datetime | None
    expires_at: datetime | None
    usage_limit: int | None
    per_customer_usage_limit: int | None
    times_used: int
    is_active: bool
    is_automatic: bool = False
    first_order_only: bool = False
    min_quantity: int | None = None
    buy_quantity: int | None = None
    get_quantity: int | None = None
    category_ids: list[UUID] = []
    valid_weekdays: list[int] = []
    created_at: datetime


class CouponApplyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=50)


class CouponApplyResponse(BaseModel):
    code: str
    discount_amount: Decimal
    currency: str
    discount_type: DiscountType | None = None
    free_shipping: bool = Field(
        default=False, description="The coupon removes the delivery charge at checkout"
    )


class OfferRead(BaseModel):
    """A live automatic discount the storefront can advertise."""

    code: str
    discount_type: DiscountType
    discount_value: Decimal
    min_order_amount: Decimal | None
    min_quantity: int | None
    buy_quantity: int | None
    get_quantity: int | None
    first_order_only: bool
    category_ids: list[UUID]
    expires_at: datetime | None
    currency: str