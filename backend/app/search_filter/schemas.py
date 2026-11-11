from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.search_filter.constants import SearchSort


@dataclass(frozen=True)
class ProductFilters:
    """Everything the storefront may narrow a product search by."""

    search: str | None = None
    category_id: uuid.UUID | None = None
    gender: str | None = None
    brand: str | None = None
    fabric: str | None = None
    occasion: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    color: str | None = None
    size: str | None = None
    min_rating: float | None = None
    max_rating: float | None = None
    sort: SearchSort = SearchSort.RECOMMENDED


class VariantAttributes(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    variant_id: uuid.UUID
    options: dict[str, str] = Field(default_factory=dict)


class ProductDiscoveryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    brand: str | None = None
    gender: str | None = None
    fabric: str | None = None
    occasion: str | None = None
    sleeve: str | None = None
    neckline: str | None = None
    category_id: uuid.UUID
    price: Decimal | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    rating: float | None = None
    variants: list[VariantAttributes] = Field(default_factory=list)


class SuggestionItem(BaseModel):
    title: str
