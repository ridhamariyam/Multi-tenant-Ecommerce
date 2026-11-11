from __future__ import annotations

from decimal import Decimal

from pydantic import Field, model_validator

from app.core.schemas import StrictModel


class QueryUnderstandingInput(StrictModel):
    """A shopper's raw product-finding message."""

    message: str = Field(max_length=1000)


class SearchCriteria(StrictModel):
    """Recognized fields that can be passed to the existing ProductFilters."""

    search: str | None = None
    fabric: str | None = None
    occasion: str | None = None
    color: str | None = None
    size: str | None = None
    min_price: Decimal | None = Field(default=None, ge=0)
    max_price: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _valid_price_range(self) -> SearchCriteria:
        if (
            self.min_price is not None
            and self.max_price is not None
            and self.min_price > self.max_price
        ):
            raise ValueError("min_price cannot be greater than max_price")
        return self
