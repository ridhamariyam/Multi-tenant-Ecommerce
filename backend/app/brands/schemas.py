from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.brands.constants import BrandRole, MemberStatus
from app.core.slugs import SLUG_PATTERN
from app.stores.models import SUBDOMAIN_PATTERN
from app.stores.schemas import StoreRead
from app.tenants.constants import CURRENCY_CODE_LENGTH, DEFAULT_CURRENCY


LowerEmail = Annotated[EmailStr, AfterValidator(lambda value: value.strip().lower())]


class BrandRegister(BaseModel):
    name: str = Field(min_length=1, max_length=150)
    slug: str | None = Field(
        default=None, min_length=2, max_length=63, pattern=SLUG_PATTERN,
        description="Defaults to one made from the name",
    )
    subdomain: str | None = Field(
        default=None, min_length=2, max_length=63, pattern=SUBDOMAIN_PATTERN,
        description="Defaults to the slug",
    )
    description: str | None = Field(default=None, max_length=2000)
    contact_email: LowerEmail | None = None
    phone: str | None = Field(default=None, max_length=20)
    currency: str = Field(
        default=DEFAULT_CURRENCY, min_length=CURRENCY_CODE_LENGTH, max_length=CURRENCY_CODE_LENGTH
    )


    @field_validator("currency")
    @classmethod
    def _upper(cls, value: str) -> str:
        return value.upper()


class BrandUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    logo_url: str | None = Field(default=None, max_length=2048)
    contact_email: LowerEmail | None = None
    phone: str | None = Field(default=None, max_length=20)



class BrandRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    contact_email: str | None
    phone: str | None
    currency: str
    status: str
    owner_account_id: UUID | None
    created_at: datetime
    updated_at: datetime


class BrandToken(BaseModel):
    """A short-lived token for one brand's admin API. Re-request it with the
    platform session when it expires; there is no brand refresh token."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    brand_id: UUID
    membership_id: UUID
    role: str


class BrandMembershipRead(BaseModel):
    membership_id: UUID
    role: str
    brand: BrandRead
    store: StoreRead | None


class BrandRegistered(BaseModel):
    brand: BrandRead
    store: StoreRead
    token: BrandToken


AssignableRole = Literal[
    BrandRole.ADMIN.value, BrandRole.PRODUCT_MANAGER.value, BrandRole.ORDER_MANAGER.value
]


class MemberCreate(BaseModel):
    email: LowerEmail = Field(description="An existing merchant account's email")
    role: AssignableRole



class MemberUpdate(BaseModel):
    role: AssignableRole | None = None
    status: Literal[MemberStatus.ACTIVE.value, MemberStatus.REMOVED.value] | None = None


class MemberRead(BaseModel):
    id: UUID
    account_id: UUID
    email: str
    name: str | None
    role: str
    status: str
    created_at: datetime
