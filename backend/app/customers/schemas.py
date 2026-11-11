from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.addresses.schemas import AddressRead
from app.core.pagination import PageParams
from app.core.schemas import StrictModel, not_blank
from app.customers.models import MAX_NOTE_LENGTH

MAX_TAGS = 20
MAX_TAG_LENGTH = 40


class CustomerQuery(PageParams):
    search: str | None = Field(default=None, max_length=100, description="Name, email or phone")
    tag: str | None = Field(default=None, max_length=MAX_TAG_LENGTH)
    status: Literal["ACTIVE", "INACTIVE", "DELETED"] | None = None
    blocked: bool | None = Field(default=None, description="Only customers blocked from ordering")
    sort: Literal["newest", "total_spent", "orders", "last_order"] = "newest"


class CustomerSummary(BaseModel):
    id: UUID
    name: str | None
    email: str | None
    phone: str | None
    status: str
    is_verified: bool
    tags: list[str]
    order_blocked: bool = False
    order_blocked_at: datetime | None = None
    order_block_reason: str | None = None
    total_orders: int
    total_spent: Decimal
    last_order_at: datetime | None
    created_at: datetime


class CustomerNoteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    author_id: UUID | None
    author_name: str | None
    body: str
    created_at: datetime


class CustomerDetail(CustomerSummary):
    first_order_at: datetime | None
    is_returning: bool = Field(description="More than one order")
    cancelled_orders: int
    returned_orders: int
    addresses: list[AddressRead]
    notes: list[CustomerNoteRead]
    currency: str


class CustomerTagsUpdate(StrictModel):
    tags: list[str] = Field(max_length=MAX_TAGS)

    @field_validator("tags")
    @classmethod
    def _clean(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for tag in value:
            tag = tag.strip()
            if not tag:
                continue
            if len(tag) > MAX_TAG_LENGTH:
                raise ValueError(f"tags must be at most {MAX_TAG_LENGTH} characters")
            if tag.lower() not in {t.lower() for t in cleaned}:
                cleaned.append(tag)
        return cleaned


class CustomerBlockUpdate(StrictModel):
    blocked: bool
    reason: str | None = Field(default=None, max_length=200)


class CustomerNoteCreate(StrictModel):
    body: str = Field(min_length=1, max_length=MAX_NOTE_LENGTH)

    _strip = field_validator("body")(not_blank)
