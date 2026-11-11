from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.auth.schemas import NormalizedPhone
from app.catalogue.constants import PRICE_SCALE
from app.cod.constants import MAX_REASON_LENGTH, BlacklistSource, CodUnavailableReason
from app.core.money import MAX_MONEY
from app.core.pagination import PageParams
from app.core.schemas import StrictModel

Money = Field(default=None, ge=0, le=MAX_MONEY, decimal_places=PRICE_SCALE)


class CodSettingsUpdate(StrictModel):
    is_enabled: bool = True
    min_order_amount: Decimal | None = Money
    max_order_amount: Decimal | None = Money
    fee_amount: Decimal = Field(
        default=Decimal("0.00"), ge=0, le=MAX_MONEY, decimal_places=PRICE_SCALE
    )
    advance_amount: Decimal | None = Field(
        default=None, gt=0, le=MAX_MONEY, decimal_places=PRICE_SCALE
    )
    auto_blacklist_threshold: int | None = Field(
        default=None, ge=1, le=100, description="Undelivered COD orders before auto-block"
    )

    @model_validator(mode="after")
    def _limits_ordered(self) -> CodSettingsUpdate:
        if (
            self.min_order_amount is not None
            and self.max_order_amount is not None
            and self.min_order_amount > self.max_order_amount
        ):
            raise ValueError("min_order_amount must not exceed max_order_amount")
        return self


class CodSettingsRead(BaseModel):
    is_enabled: bool = True
    min_order_amount: Decimal | None = None
    max_order_amount: Decimal | None = None
    fee_amount: Decimal = Decimal("0.00")
    advance_amount: Decimal | None = None
    auto_blacklist_threshold: int | None = None


class BlacklistCreate(StrictModel):
    phone: NormalizedPhone
    reason: str | None = Field(default=None, max_length=MAX_REASON_LENGTH)


class BlacklistRead(BaseModel):
    id: UUID
    phone: str
    reason: str | None
    source: BlacklistSource
    created_at: datetime


class BlacklistQuery(PageParams):
    source: BlacklistSource | None = None


class CodAvailability(BaseModel):
    """Whether this order may be paid cash on delivery, and what that costs."""

    available: bool
    reason: CodUnavailableReason | None = None
    message: str | None = None
    fee: Decimal = Decimal("0.00")
    advance_amount: Decimal = Decimal("0.00")


class CodReportQuery(StrictModel):
    start_date: date
    end_date: date

    @model_validator(mode="after")
    def _ordered(self) -> CodReportQuery:
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        return self


class CodReportRead(BaseModel):
    start_date: date
    end_date: date
    total_orders: int
    delivered_orders: int
    returned_orders: int
    cancelled_orders: int
    in_progress_orders: int
    delivery_rate: float = Field(description="Delivered / (delivered + returned), 0-100")
    order_value: Decimal = Field(description="Total value of all COD orders placed")
    delivered_value: Decimal
    returned_value: Decimal
    cash_collected: Decimal = Field(description="COD payments marked PAID on delivery")
    advance_collected: Decimal
    fees_collected: Decimal = Field(description="COD fees on delivered orders")
    net_revenue: Decimal = Field(description="Cash collected plus advances received")
    cash_remitted: Decimal = Field(
        default=Decimal("0.00"), description="Collected cash the courier has paid over"
    )
    cash_outstanding: Decimal = Field(
        default=Decimal("0.00"), description="Collected cash not yet received from the courier"
    )
    currency: str


class RemittanceCreate(StrictModel):
    """Cash the courier has paid over, for these collected COD payments."""

    payment_ids: list[UUID] = Field(min_length=1, max_length=500)
    reference: str = Field(min_length=1, max_length=100, description="UTR / settlement id")
    remitted_on: date | None = Field(default=None, description="Defaults to today")


class RemittanceResult(BaseModel):
    remitted: int
    amount: Decimal


class CollectionQuery(PageParams):
    status: Literal["outstanding", "remitted"] = "outstanding"


class CollectionRow(BaseModel):
    payment_id: UUID
    order_id: UUID
    order_number: str
    amount: Decimal
    collected_at: datetime
    remitted_at: datetime | None
    remittance_reference: str | None
