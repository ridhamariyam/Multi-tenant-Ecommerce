from __future__ import annotations

from pydantic import BaseModel, ConfigDict, model_validator


class StrictModel(BaseModel):
    """Request payload that rejects any field it does not declare."""

    model_config = ConfigDict(extra="forbid")


class PartialUpdate(StrictModel):
    """Patch payload that has to carry at least one field."""

    @model_validator(mode="after")
    def _require_a_field(self) -> PartialUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


def not_blank(value: str | None) -> str | None:
    """Trim a string and refuse one that is empty; None passes through."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        raise ValueError("must not be blank")
    return value


def blank_to_none(value: str | None) -> str | None:
    """Trim a string; an empty one means "not set"."""
    if value is None:
        return None
    return value.strip() or None
