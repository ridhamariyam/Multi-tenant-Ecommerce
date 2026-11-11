"""Resolve the merchant account behind a platform session token."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import bearer_scheme
from app.core.database import get_db
from app.core.error_codes import AuthErrorCode, MerchantErrorCode
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.merchants.models import MerchantAccount
from app.merchants.security import decode_merchant_token


async def get_current_account(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> MerchantAccount:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Not authenticated", error_code=AuthErrorCode.NOT_AUTHENTICATED)
    payload = decode_merchant_token(credentials.credentials, expected_type="merchant_access")
    account = await session.get(MerchantAccount, payload.account_id)
    if account is None or not account.is_active:
        raise AuthenticationError(
            "Invalid authentication credentials", error_code=AuthErrorCode.INVALID_TOKEN
        )
    return account


CurrentAccount = Annotated[MerchantAccount, Depends(get_current_account)]


async def require_platform_admin(account: CurrentAccount) -> MerchantAccount:
    if not account.is_platform_admin:
        raise PermissionDeniedError(
            "Platform administrators only",
            error_code=MerchantErrorCode.PLATFORM_ADMIN_REQUIRED,
        )
    return account


PlatformAdmin = Annotated[MerchantAccount, Depends(require_platform_admin)]
