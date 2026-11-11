from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.schemas import PartialUpdate, StrictModel, not_blank
from app.returns.models import MAX_REASON_LENGTH


class ReturnReasonCreate(StrictModel):
    label: str = Field(min_length=1, max_length=MAX_REASON_LENGTH)
    is_active: bool = True

    _clean = field_validator("label")(not_blank)


class ReturnReasonUpdate(PartialUpdate):
    label: str | None = Field(default=None, min_length=1, max_length=MAX_REASON_LENGTH)
    is_active: bool | None = None
    position: int | None = Field(default=None, ge=0)

    _clean = field_validator("label")(not_blank)


class ReturnReasonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    label: str
    is_active: bool
    position: int
