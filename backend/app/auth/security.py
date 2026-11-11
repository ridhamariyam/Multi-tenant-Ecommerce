from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

import anyio.to_thread
import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import PwdlibError

from app.core.config import get_settings
from app.core.error_codes import AuthErrorCode
from app.core.exceptions import AuthenticationError

TokenType = Literal["access", "refresh"]

_hasher = PasswordHash.recommended()

_DUMMY_HASH: str | None = None


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    tenant_id: str
    token_type: TokenType
    role: str | None = None
    # Set on tokens a merchant account obtained for one brand: the
    # brand_members row that must still be active for the token to count.
    membership_id: str | None = None


def _hash_sync(secret: str) -> str:
    return _hasher.hash(secret)


def _verify_sync(secret: str, hashed: str) -> bool:
    try:
        return _hasher.verify(secret, hashed)
    except (ValueError, TypeError, PwdlibError):
        return False


async def hash_password(password: str) -> str:
    return await anyio.to_thread.run_sync(_hash_sync, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await anyio.to_thread.run_sync(_verify_sync, password, password_hash)


async def spend_dummy_verification() -> None:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = await hash_password(uuid.uuid4().hex)
    await verify_password("not-the-password", _DUMMY_HASH)


def _create(
    *,
    user_id: UUID,
    tenant_id: UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    secret: str,
    extra: dict[str, Any],
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
        **extra,
    }
    return jwt.encode(claims, secret, algorithm=settings.jwt_algorithm)


def create_access_token(
    *,
    user_id: UUID,
    tenant_id: UUID,
    role: str,
    membership_id: UUID | None = None,
    expires_minutes: int | None = None,
) -> str:
    settings = get_settings()
    extra: dict[str, Any] = {"role": role}
    if membership_id is not None:
        extra["mbr"] = str(membership_id)
    return _create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_type="access",
        expires_delta=timedelta(
            minutes=expires_minutes or settings.access_token_expire_minutes
        ),
        secret=settings.jwt_secret,
        extra=extra,
    )


def create_refresh_token(*, user_id: UUID, tenant_id: UUID) -> str:
    settings = get_settings()
    return _create(
        user_id=user_id,
        tenant_id=tenant_id,
        token_type="refresh",
        expires_delta=timedelta(days=settings.refresh_token_expire_days),
        secret=settings.jwt_refresh_secret,
        extra={"jti": uuid.uuid4().hex},
    )


def hash_refresh_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_token(token: str, *, expected_type: TokenType) -> TokenPayload:
    settings = get_settings()
    secret = settings.jwt_secret if expected_type == "access" else settings.jwt_refresh_secret
    try:
        claims = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError(
            "Token has expired", error_code=AuthErrorCode.TOKEN_EXPIRED
        ) from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError(
            "Invalid authentication token",
            error_code=AuthErrorCode.INVALID_TOKEN,
        ) from exc

    user_id = claims.get("sub")
    tenant_id = claims.get("tenant_id")
    if claims.get("type") != expected_type or not user_id or not tenant_id:
        raise AuthenticationError(
            "Invalid authentication token",
            error_code=AuthErrorCode.INVALID_TOKEN,
        )

    return TokenPayload(
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        token_type=expected_type,
        role=claims.get("role"),
        membership_id=claims.get("mbr"),
    )
