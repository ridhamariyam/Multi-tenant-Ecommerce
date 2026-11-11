from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import StrictModel

MAX_RANGE_DAYS = 366

# json = the API response; the others are downloads of the same rows.
ExportFormat = Literal["json", "csv", "xlsx", "pdf"]


def _today() -> date:
    return datetime.now(timezone.utc).date()


class DateRange(StrictModel):
    start_date: date = Field(default_factory=lambda: _today() - timedelta(days=29))
    end_date: date = Field(default_factory=_today)
    format: ExportFormat = "json"

    @model_validator(mode="after")
    def _ordered(self) -> DateRange:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        if (self.end_date - self.start_date).days > MAX_RANGE_DAYS:
            raise ValueError(f"a report can cover at most {MAX_RANGE_DAYS} days")
        return self


class SalesQuery(DateRange):
    group_by: Literal["day", "week", "month"] = "day"


class LocationQuery(DateRange):
    level: Literal["state", "city"] = "state"


class InventoryQuery(StrictModel):
    stock_status: Literal["all", "in", "low", "out"] = "all"
    format: ExportFormat = "json"


class UnsoldQuery(StrictModel):
    days: int = Field(default=30, ge=1, le=365)
    format: ExportFormat = "json"


class ReturnsQuery(DateRange):
    breakdown: Literal["product", "reason"] = Field(
        default="product", description="Which table a download contains"
    )


class CustomersQuery(DateRange):
    top: int = Field(default=20, ge=1, le=100)


class SalesRow(BaseModel):
    period: date
    orders: int
    cancelled_orders: int
    returned_orders: int
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    cod_fee: Decimal
    tax: Decimal
    revenue: Decimal
    returned_value: Decimal
    net_revenue: Decimal
    average_order_value: Decimal


class SalesSummary(BaseModel):
    orders: int
    cancelled_orders: int
    returned_orders: int
    subtotal: Decimal
    discount: Decimal
    shipping: Decimal
    cod_fee: Decimal
    tax: Decimal
    revenue: Decimal
    returned_value: Decimal
    net_revenue: Decimal
    average_order_value: Decimal


class SalesReport(BaseModel):
    group_by: str
    rows: list[SalesRow]
    summary: SalesSummary
    currency: str


class ProductSalesRow(BaseModel):
    product_id: UUID
    product_name: str
    units_sold: int
    orders: int
    gross_sales: Decimal
    discounts: Decimal
    net_sales: Decimal


class CategorySalesRow(BaseModel):
    category_id: UUID
    category_name: str
    units_sold: int
    orders: int
    gross_sales: Decimal
    discounts: Decimal
    net_sales: Decimal


class LocationSalesRow(BaseModel):
    state: str | None
    city: str | None = None
    orders: int
    revenue: Decimal
    returned_orders: int


class InventoryRow(BaseModel):
    product_id: UUID
    product_name: str
    variant_id: UUID
    sku: str
    variant_name: str
    variant_status: str
    available_quantity: int
    reserved_quantity: int
    sellable_quantity: int
    low_stock_threshold: int
    stock_status: str
    unit_price: Decimal
    stock_value: Decimal


class UnsoldRow(BaseModel):
    product_id: UUID
    product_name: str
    variant_id: UUID
    sku: str
    sellable_quantity: int
    last_sold_at: datetime | None
    listed_since: datetime


class TopCustomerRow(BaseModel):
    customer_id: UUID
    name: str | None
    email: str | None
    phone: str | None
    orders: int
    total_spent: Decimal
    last_order_at: datetime | None


class CustomersReport(BaseModel):
    start_date: date
    end_date: date
    customers_ordering: int
    new_customers: int
    returning_customers: int
    returning_pct: float | None
    signups: int
    top_customers: list[TopCustomerRow]


class CouponReportRow(BaseModel):
    coupon_id: UUID
    code: str
    discount_type: str
    is_automatic: bool
    orders: int
    discount_given: Decimal
    order_revenue: Decimal
    customers: int


class ReturnedProductRow(BaseModel):
    product_id: UUID
    product_name: str
    units_returned: int
    orders: int


class ReturnReasonRow(BaseModel):
    reason: str
    orders: int
    returned_value: Decimal


class ReturnsReport(BaseModel):
    start_date: date
    end_date: date
    returned_orders: int
    returned_value: Decimal
    cancelled_orders: int
    cancelled_value: Decimal
    delivered_orders: int
    return_rate: float | None
    by_product: list[ReturnedProductRow]
    by_reason: list[ReturnReasonRow] = []


class AnalyticsReport(BaseModel):
    start_date: date
    end_date: date
    orders: int
    revenue: Decimal
    average_order_value: Decimal
    cancelled_orders: int
    cancellation_rate: float | None
    returned_orders: int
    return_rate: float | None
    cod_orders: int
    cod_revenue: Decimal
    prepaid_orders: int
    prepaid_revenue: Decimal
    cod_share_pct: float | None
    new_customers: int
    returning_customers: int
    top_products: list[ProductSalesRow]
    currency: str
