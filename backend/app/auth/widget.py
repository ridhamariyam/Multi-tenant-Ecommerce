from __future__ import annotations

from typing import Any

import httpx

from app.auth.phone import normalize_phone
from app.core.config import get_settings
from app.core.error_codes import AuthErrorCode
from app.core.exceptions import AuthenticationError, ServiceUnavailableError

UNVERIFIED = "Could not verify that number"
UNAVAILABLE = "Unable to verify your number right now"
_IDENTIFIER_KEYS = ("message", "mobile", "identifier", "phone", "number")
_MAX_SEARCH_DEPTH = 3
# MSG91 answers these when the fault is ours, not the user's: 201 = auth key
# rejected, 418 = this server's IP is not whitelisted against the auth key.
_OUR_FAULT_CODES = frozenset({"201", "418"})


async def verify_access_token(access_token: str) -> str:
    """
    Ask MSG91 to verify a widget access token, and return the number it attests to.
    """
    settings = get_settings()

    if not settings.msg91_auth_key:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=AuthErrorCode.OTP_PROVIDER_UNAVAILABLE,
        )

    try:
        async with httpx.AsyncClient(timeout=settings.msg91_timeout_seconds) as client:
            response = await client.post(
                settings.msg91_widget_verify_url,
                json={
                    "authkey": settings.msg91_auth_key,
                    "access-token": access_token,
                },
                headers={"Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=AuthErrorCode.OTP_PROVIDER_UNAVAILABLE,
        ) from exc

    return _identity_from(response)


def _identity_from(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        payload = None

    outcome = ""
    if isinstance(payload, dict):
        outcome = str(payload.get("type", "")).lower()

    if response.status_code >= httpx.codes.INTERNAL_SERVER_ERROR or (
        response.status_code == httpx.codes.TOO_MANY_REQUESTS
    ):
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=AuthErrorCode.OTP_PROVIDER_UNAVAILABLE,
        )

    code = str(payload.get("code", "")) if isinstance(payload, dict) else ""
    if code in _OUR_FAULT_CODES:
        raise ServiceUnavailableError(
            UNAVAILABLE,
            error_code=AuthErrorCode.OTP_PROVIDER_UNAVAILABLE,
        )

    if response.status_code != httpx.codes.OK or outcome != "success":
        raise AuthenticationError(UNVERIFIED, error_code=AuthErrorCode.INVALID_OTP)

    phone = _phone_from(payload)

    if phone is None:
        raise AuthenticationError(UNVERIFIED, error_code=AuthErrorCode.INVALID_OTP)

    return phone


def _phone_from(payload: dict[str, Any], depth: int = 0) -> str | None:
    """
    Look for a phone number in the payload, which may be nested.
    """
    if depth > _MAX_SEARCH_DEPTH:
        return None

    for key in _IDENTIFIER_KEYS:
        value = payload.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            value = format(int(value), "d")
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            return normalize_phone(value)
        except ValueError:
            continue

    for nested in payload.values():
        if isinstance(nested, dict):
            found = _phone_from(nested, depth + 1)
            if found is not None:
                return found

    return None
