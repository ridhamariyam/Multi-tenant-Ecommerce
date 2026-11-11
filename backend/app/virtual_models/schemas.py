from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.virtual_models.constants import GARMENT_TYPES, GENDER_PRESENTATIONS, MODEL_TYPES

Gender = Literal[GENDER_PRESENTATIONS]  # type: ignore[valid-type]
ModelType = Literal[MODEL_TYPES]  # type: ignore[valid-type]
Garment = Literal[GARMENT_TYPES]  # type: ignore[valid-type]


def _clean_list(values: list[str]) -> list[str]:
    seen: list[str] = []
    for value in values:
        item = value.strip().lower()
        if item and item not in seen:
            seen.append(item)
    return seen


def _strip_name(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


class VirtualModelCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    gender_presentation: Gender
    model_type: ModelType = "FULL_BODY"
    available_categories: list[str] = Field(default_factory=list, max_length=20)
    supported_garments: list[Garment] = Field(default_factory=list)
    license_note: str | None = Field(default=None, max_length=500)

    _strip = field_validator("name")(_strip_name)

    @field_validator("available_categories")
    @classmethod
    def _categories(cls, value: list[str]) -> list[str]:
        cleaned = _clean_list(value)
        if any(len(v) > 50 for v in cleaned):
            raise ValueError("categories are at most 50 characters")
        return cleaned

    @field_validator("supported_garments")
    @classmethod
    def _garments(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class VirtualModelUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=2000)
    gender_presentation: Gender | None = None
    model_type: ModelType | None = None
    available_categories: list[str] | None = Field(default=None, max_length=20)
    supported_garments: list[Garment] | None = None
    license_note: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

    _strip = field_validator("name")(_strip_name)

    @field_validator("available_categories")
    @classmethod
    def _categories(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else VirtualModelCreate._categories(value)

    @field_validator("supported_garments")
    @classmethod
    def _garments(cls, value: list[str] | None) -> list[str] | None:
        return None if value is None else _clean_list(value)


class PoseRead(BaseModel):
    id: UUID
    label: str | None
    url: str
    width: int | None
    height: int | None
    sort_order: int


class VirtualModelRead(BaseModel):
    id: UUID
    name: str
    description: str | None
    gender_presentation: str
    model_type: str
    available_categories: list[str]
    supported_garments: list[str]
    image_url: str | None
    poses: list[PoseRead]
    is_active: bool
    created_at: datetime


class VirtualModelAdminRead(VirtualModelRead):
    license_note: str | None
    updated_at: datetime
