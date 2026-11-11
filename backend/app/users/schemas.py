from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.auth.permissions import ALL_PERMISSIONS
from app.auth.schemas import MAX_PASSWORD_LENGTH, MIN_PASSWORD_LENGTH, NormalizedPhone
from app.core.pagination import PageParams
from app.core.schemas import PartialUpdate, StrictModel

StaffRole = Literal["ADMIN", "STAFF"]
StaffStatus = Literal["ACTIVE", "INACTIVE"]
Password = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_LENGTH)


def _check_permissions(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    unknown = sorted(set(value) - ALL_PERMISSIONS)
    if unknown:
        raise ValueError(f"unknown permissions: {', '.join(unknown)}")
    return sorted(set(value))



# Staff accounts: individual logins, roles and permissions (admin-only).


class StaffCreate(StrictModel):
    name: str = Field(min_length=1, max_length=150)
    email: EmailStr
    phone: NormalizedPhone
    password: str = Password
    role: StaffRole = "STAFF"
    permissions: list[str] = Field(default_factory=list)

    _valid_permissions = field_validator("permissions")(_check_permissions)


class StaffUpdate(PartialUpdate):
    name: str | None = Field(default=None, min_length=1, max_length=150)
    role: StaffRole | None = None
    permissions: list[str] | None = None
    status: StaffStatus | None = None

    _valid_permissions = field_validator("permissions")(_check_permissions)


class StaffPasswordReset(StrictModel):
    password: str = Password


class StaffQuery(PageParams):
    search: str | None = Field(default=None, max_length=100)
    status: StaffStatus | None = None


class StaffRead(BaseModel):
    id: UUID
    name: str | None
    email: str | None
    phone: str | None
    role: str
    status: str
    permissions: list[str] | None = Field(
        description="Granted permissions; null = legacy staff access (STAFF) / everything (ADMIN)"
    )
    effective_permissions: list[str]
    created_at: datetime



class PermissionRead(BaseModel):
    key: str
    description: str
