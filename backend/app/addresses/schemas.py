from __future__ import annotations

import re
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from app.addresses.models import (
    MAX_CITY_LENGTH,
    MAX_LINE_LENGTH,
    MAX_NAME_LENGTH,
    MAX_POSTAL_CODE_LENGTH,
)
from app.auth.schemas import NormalizedPhone
from app.core.schemas import PartialUpdate, StrictModel, blank_to_none, not_blank

INDIA = {"india", "in", "ind"}
INDIA_PIN = re.compile(r"^[1-9]\d{5}$")
POSTAL_CODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 -]{2,9}$")


def _check_postal_code(value: str, info: ValidationInfo) -> str:
    code = not_blank(value)
    country = (info.data.get("country") or "").strip().lower()
    pattern = INDIA_PIN if country in INDIA else POSTAL_CODE
    if not pattern.match(code):
        raise ValueError("Not a valid postal code")
    return code


def _check_postal_code_optional(value: str | None, info: ValidationInfo) -> str | None:
    return None if value is None else _check_postal_code(value, info)


class AddressCreate(StrictModel):
    full_name: str = Field(max_length=MAX_NAME_LENGTH)
    phone: NormalizedPhone
    address_line_1: str = Field(max_length=MAX_LINE_LENGTH)
    address_line_2: str | None = Field(default=None, max_length=MAX_LINE_LENGTH)
    city: str = Field(max_length=MAX_CITY_LENGTH)
    state: str = Field(max_length=MAX_CITY_LENGTH)
    country: str = Field(max_length=MAX_CITY_LENGTH)
    postal_code: str = Field(max_length=MAX_POSTAL_CODE_LENGTH)
    is_default: bool = False

    _strip_full_name = field_validator("full_name")(not_blank)
    _strip_line_1 = field_validator("address_line_1")(not_blank)
    _strip_line_2 = field_validator("address_line_2")(blank_to_none)
    _strip_city = field_validator("city")(not_blank)
    _strip_state = field_validator("state")(not_blank)
    _strip_country = field_validator("country")(not_blank)
    _check_postal_code = field_validator("postal_code")(_check_postal_code)


class AddressUpdate(PartialUpdate):
    full_name: str | None = Field(default=None, max_length=MAX_NAME_LENGTH)
    phone: NormalizedPhone | None = None
    address_line_1: str | None = Field(default=None, max_length=MAX_LINE_LENGTH)
    address_line_2: str | None = Field(default=None, max_length=MAX_LINE_LENGTH)
    city: str | None = Field(default=None, max_length=MAX_CITY_LENGTH)
    state: str | None = Field(default=None, max_length=MAX_CITY_LENGTH)
    country: str | None = Field(default=None, max_length=MAX_CITY_LENGTH)
    postal_code: str | None = Field(default=None, max_length=MAX_POSTAL_CODE_LENGTH)
    is_default: bool | None = None

    _strip_full_name = field_validator("full_name")(not_blank)
    _strip_line_1 = field_validator("address_line_1")(not_blank)
    _strip_line_2 = field_validator("address_line_2")(blank_to_none)
    _strip_city = field_validator("city")(not_blank)
    _strip_state = field_validator("state")(not_blank)
    _strip_country = field_validator("country")(not_blank)
    _check_postal_code = field_validator("postal_code")(_check_postal_code_optional)


class AddressRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    full_name: str
    phone: str
    address_line_1: str
    address_line_2: str | None
    city: str
    state: str
    postal_code: str
    country: str
    is_default: bool
