from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.stores.constants import STORE_THEMES
from app.stores.models import COLOR_PATTERN, SUBDOMAIN_PATTERN

Theme = Literal[STORE_THEMES]  # type: ignore[valid-type]

# A hostname of two or more DNS labels, e.g. shop.example.com.
DOMAIN_PATTERN = r"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"


class StoreRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    subdomain: str
    url: str = Field(description="Where the storefront is served on the platform")
    theme: str
    logo_url: str | None
    favicon_url: str | None
    primary_color: str | None
    secondary_color: str | None
    published: bool
    published_at: datetime | None


class StoreUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    subdomain: str | None = Field(default=None, min_length=2, max_length=63, pattern=SUBDOMAIN_PATTERN)
    theme: Theme | None = None
    logo_url: str | None = Field(default=None, max_length=2048)
    favicon_url: str | None = Field(default=None, max_length=2048)
    primary_color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    secondary_color: str | None = Field(default=None, pattern=COLOR_PATTERN)


class StorePublish(BaseModel):
    published: bool = True


class DomainCreate(BaseModel):
    domain: str = Field(min_length=4, max_length=253, pattern=DOMAIN_PATTERN)
    is_primary: bool = False

    @field_validator("domain", mode="before")
    @classmethod
    def _normalize(cls, value: object) -> object:
        return value.strip().lower().rstrip(".") if isinstance(value, str) else value


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    domain: str
    is_primary: bool
    verified_at: datetime | None
    verification_record: str | None = Field(
        default=None,
        description="TXT record to add at _cliq-verify.<domain> to prove ownership",
    )
    created_at: datetime


class DomainCheckRead(BaseModel):
    """The outcome of looking up a domain's verification TXT record."""

    domain: DomainRead
    verified: bool
    record_name: str
    expected: str
    found: list[str]
    problem: str | None
