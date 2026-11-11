from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import PageParams


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_id: UUID | None
    actor_name: str | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    summary: str | None
    changes: dict | list | None
    ip_address: str | None
    created_at: datetime


class AuditLogQuery(PageParams):
    actor_id: UUID | None = None
    entity_type: str | None = Field(default=None, max_length=50)
    entity_id: str | None = Field(default=None, max_length=64)
    action: str | None = Field(default=None, max_length=80, description="Prefix, e.g. 'order.'")
    start_date: date | None = None
    end_date: date | None = None
