"""Platform session tokens for merchant accounts.

These are deliberately a different token type from the per-brand tokens in
app.auth.security: `decode_token(expected_type="access")` refuses them, so a
platform session can never be used directly against a brand's admin API. It
must be exchanged for a brand token, which re-checks the membership.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal

import jwt

from app.core.config import get_settings
from app.core.error_codes import AuthErrorCode
from app.core.exceptions import AuthenticationError

MerchantTokenType = Literal["merchant_access", "merchant_refresh"]


@dataclass(frozen=True)
class MerchantTokenPayload:
    account_id: uuid.UUID
    token_type: MerchantTokenType


def _secret(token_type: MerchantTokenType) -> str:
    settings = get_settings()
    return settings.jwt_secret if token_type == "merchant_access" else settings.jwt_refresh_secret


def create_merchant_token(account_id: uuid.UUID, token_type: MerchantTokenType) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    lifetime = (
        timedelta(minutes=settings.merchant_access_token_expire_minutes)
        if token_type == "merchant_access"
        else timedelta(days=settings.merchant_refresh_token_expire_days)
    )
    claims = {
        "sub": str(account_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(claims, _secret(token_type), algorithm=settings.jwt_algorithm)


def decode_merchant_token(token: str, *, expected_type: MerchantTokenType) -> MerchantTokenPayload:
    settings = get_settings()
    try:
        claims = jwt.decode(token, _secret(expected_type), algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired", error_code=AuthErrorCode.TOKEN_EXPIRED) from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(
            "Invalid authentication token", error_code=AuthErrorCode.INVALID_TOKEN
        ) from exc

    if claims.get("type") != expected_type or "tenant_id" in claims:
        raise AuthenticationError(
            "Invalid authentication token", error_code=AuthErrorCode.INVALID_TOKEN
        )
    try:
        account_id = uuid.UUID(str(claims.get("sub")))
    except ValueError as exc:
        raise AuthenticationError(
            "Invalid authentication token", error_code=AuthErrorCode.INVALID_TOKEN
        ) from exc
    return MerchantTokenPayload(account_id=account_id, token_type=expected_type)


def merchant_access_lifetime_seconds() -> int:
    return get_settings().merchant_access_token_expire_minutes * 60
