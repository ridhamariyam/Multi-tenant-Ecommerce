"""A small Google Sheets API client, authenticated as the platform's service account.

Only what the order export needs: make sure a worksheet exists with a header
row, and append rows to it. Values are written RAW, so text a shopper typed
(a name starting with "=") is stored as text and never evaluated as a formula.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import re
import threading
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx

from app.core.config import get_settings

SCOPES = ("https://www.googleapis.com/auth/spreadsheets",)

_SPREADSHEET_URL = re.compile(r"/spreadsheets/d/([A-Za-z0-9_-]+)")
_SPREADSHEET_ID = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


class SheetsError(Exception):
    """A Sheets call failed; `message` is safe to show a store admin."""

    def __init__(self, message: str, *, kind: str = "unavailable") -> None:
        super().__init__(message)
        self.message = message
        # not_configured | access_denied | not_found | unavailable
        self.kind = kind


def parse_spreadsheet_id(value: str) -> str | None:
    """The spreadsheet id from a sheet URL or a bare id; None if it is neither."""
    value = value.strip()
    match = _SPREADSHEET_URL.search(value)
    candidate = match.group(1) if match else value
    return candidate if _SPREADSHEET_ID.match(candidate) else None


def spreadsheet_url(spreadsheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"


def _service_account_info() -> dict[str, Any] | None:
    settings = get_settings()
    raw = settings.google_sheets_service_account_json
    if raw:
        raw = raw.strip()
        if not raw.startswith("{"):
            try:
                raw = base64.b64decode(raw, validate=True).decode()
            except (binascii.Error, UnicodeDecodeError):
                return None
        try:
            info = json.loads(raw)
        except json.JSONDecodeError:
            return None
    elif settings.google_sheets_service_account_file:
        try:
            info = json.loads(Path(settings.google_sheets_service_account_file).read_text())
        except (OSError, json.JSONDecodeError):
            return None
    else:
        return None
    if not isinstance(info, dict) or not info.get("client_email") or not info.get("private_key"):
        return None
    return info


def service_account_email() -> str | None:
    """The address a brand shares its spreadsheet with; None until configured."""
    info = _service_account_info()
    return str(info["client_email"]) if info else None


def is_configured() -> bool:
    return _service_account_info() is not None


_credentials: Any = None
_credentials_key: str | None = None
_credentials_lock = threading.Lock()


def _refreshed_token() -> str:
    """A valid access token, refreshed when it is close to expiry (blocking)."""
    global _credentials, _credentials_key

    from google.auth.transport.requests import Request
    from google.oauth2 import service_account

    info = _service_account_info()
    if info is None:
        raise SheetsError(
            "Google Sheets is not set up on the server yet.", kind="not_configured"
        )
    key = f"{info['client_email']}:{info.get('private_key_id', '')}"
    with _credentials_lock:
        if _credentials is None or _credentials_key != key:
            try:
                _credentials = service_account.Credentials.from_service_account_info(
                    info, scopes=SCOPES
                )
            except ValueError as exc:
                raise SheetsError(
                    "The Google service account key on the server is invalid.",
                    kind="not_configured",
                ) from exc
            _credentials_key = key
        if not _credentials.valid:
            try:
                _credentials.refresh(Request())
            except Exception as exc:  # google.auth.exceptions.* and transport errors
                raise SheetsError("Could not sign in to Google. Try again shortly.") from exc
        return str(_credentials.token)


async def _access_token() -> str:
    return await asyncio.to_thread(_refreshed_token)


def _a1(worksheet: str, cells: str) -> str:
    """An A1 range on a named worksheet, quoted so any tab name works."""
    escaped = worksheet.replace("'", "''")
    return quote(f"'{escaped}'!{cells}", safe="")


class SheetsClient:
    def __init__(self, spreadsheet_id: str) -> None:
        self.spreadsheet_id = spreadsheet_id
        settings = get_settings()
        self._base = f"{settings.google_sheets_api_url.rstrip('/')}/spreadsheets/{spreadsheet_id}"
        self._timeout = settings.google_sheets_timeout_seconds

    async def _call(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        token = await _access_token()
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(
                    method,
                    f"{self._base}{path}",
                    headers={"Authorization": f"Bearer {token}"},
                    **kwargs,
                )
        except httpx.HTTPError as exc:
            raise SheetsError("Could not reach Google Sheets. Try again shortly.") from exc

        if response.status_code in (401, 403):
            email = service_account_email() or "the CliQ service account"
            raise SheetsError(
                f"No access to this spreadsheet. Share it with {email} as an Editor.",
                kind="access_denied",
            )
        if response.status_code == 404:
            raise SheetsError(
                "Spreadsheet not found. Check the link or ID.", kind="not_found"
            )
        if response.status_code >= 400:
            raise SheetsError(
                f"Google Sheets rejected the request (HTTP {response.status_code})."
            )
        return response.json() if response.content else {}

    async def worksheet_titles(self) -> list[str]:
        body = await self._call("GET", "", params={"fields": "sheets.properties.title"})
        return [
            sheet.get("properties", {}).get("title", "")
            for sheet in body.get("sheets", [])
        ]

    async def ensure_worksheet(self, title: str, header: list[str]) -> None:
        """Create the tab if missing, and write the header row if the tab is empty."""
        if title not in await self.worksheet_titles():
            await self._call(
                "POST",
                ":batchUpdate",
                json={"requests": [{"addSheet": {"properties": {"title": title}}}]},
            )
        first = await self._call("GET", f"/values/{_a1(title, 'A1:A1')}")
        if not first.get("values"):
            await self._call(
                "PUT",
                f"/values/{_a1(title, 'A1')}",
                params={"valueInputOption": "RAW"},
                json={"values": [header]},
            )

    async def append_rows(self, title: str, rows: list[list[Any]]) -> None:
        if not rows:
            return
        await self._call(
            "POST",
            f"/values/{_a1(title, 'A1')}:append",
            params={"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"},
            json={"values": rows},
        )
