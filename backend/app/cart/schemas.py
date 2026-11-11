from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.catalogue.schemas import ProductImageSummary
from app.core.schemas import StrictModel

MAX_ITEM_QUANTITY = 999


class CartItemCreate(StrictModel):
    variant_id: UUID
    quantity: int = Field(default=1, ge=1, le=MAX_ITEM_QUANTITY)


class CartItemUpdate(StrictModel):
    quantity: int = Field(ge=1, le=MAX_ITEM_QUANTITY)


class CartItemRead(BaseModel):
    id: UUID
    variant_id: UUID
    product_id: UUID
    product_name: str
    variant_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal
    image: ProductImageSummary | None = None


class CartRead(BaseModel):
    id: UUID
    items: list[CartItemRead] = []
    subtotal: Decimal = Decimal("0.00")
    item_count: int = 0
    expires_at: datetime | None = Field(
        default=None, description="When the cart empties if nobody touches it again"
    )
    guest_token: str | None = Field(
        default=None,
        description="Returned once, when a guest cart is created. Send it back as X-Cart-Token.",
    )
