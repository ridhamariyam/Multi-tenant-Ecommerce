from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.merchants.constants import MIN_PASSWORD_LENGTH


class MerchantRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=128)
    name: str = Field(min_length=1, max_length=150)
    phone: str | None = Field(default=None, max_length=20)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class MerchantLogin(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, value: str) -> str:
        return value.strip().lower()


class MerchantRefresh(BaseModel):
    refresh_token: str = Field(min_length=1)


class MerchantAccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    name: str | None
    phone: str | None
    status: str
    is_platform_admin: bool
    created_at: datetime


class MerchantSession(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")
    account: MerchantAccountRead
