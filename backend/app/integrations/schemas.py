from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class IntegrationStatus(BaseModel):
    key: str
    name: str
    purpose: str
    credentials_configured: bool
    integrated: bool
    status: str
    required_settings: list[str]
    note: str


class OrderSheetSettingsRead(BaseModel):
    """Google Sheets order export for this store."""

    # Server side: is the platform's Google service account set up at all.
    credentials_configured: bool
    # Share the spreadsheet with this address (Editor) so orders can be written.
    service_account_email: str | None
    is_enabled: bool
    spreadsheet_id: str | None
    spreadsheet_url: str | None
    worksheet_name: str
    last_synced_at: datetime | None
    last_error: str | None
    last_error_at: datetime | None
    # Sales not yet in the sheet, and sales already written to it.
    pending_orders: int
    exported_orders: int


class OrderSheetSettingsUpdate(BaseModel):
    is_enabled: bool
    # The sheet's link from the browser address bar, or just its ID.
    spreadsheet: str | None = Field(default=None, max_length=500)
    worksheet_name: str = Field(default="Orders", max_length=100)


class OrderSheetSyncRead(BaseModel):
    exported: int
    pending: int
    error: str | None
