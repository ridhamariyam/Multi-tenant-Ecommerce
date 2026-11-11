from __future__ import annotations

from pydantic import BaseModel


class IntegrationStatus(BaseModel):
    key: str
    name: str
    purpose: str
    credentials_configured: bool
    integrated: bool
    status: str
    required_settings: list[str]
    note: str
