from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.request_context import client_ip
from app.core.responses import ApiResponse, ok
from app.merchants.dependencies import CurrentAccount
from app.merchants.schemas import (
    MerchantAccountRead,
    MerchantLogin,
    MerchantRefresh,
    MerchantRegister,
    MerchantSession,
)
from app.merchants.service import MerchantAuthService

router = APIRouter(prefix="/platform/auth", tags=["Platform Auth"])


async def _throttle(request: Request, scope: str, subject: str) -> str:
    settings = get_settings()
    ip = client_ip(request)
    await rate_limit.hit(
        rate_limit.key_for(f"{scope}-ip", ip),
        limit=settings.login_ip_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    key = rate_limit.key_for(scope, ip, subject)
    await rate_limit.hit(
        key,
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    return key


@router.post(
    "/register",
    response_model=ApiResponse[MerchantSession],
    status_code=status.HTTP_201_CREATED,
    summary="Create a merchant account and sign it in",
)
async def register(
    request: Request, data: MerchantRegister, session: AsyncSession = Depends(get_db)
) -> ApiResponse[MerchantSession]:
    await _throttle(request, "merchant-register", data.email)
    return ok(await MerchantAuthService(session).register(data), message="Account created")


@router.post(
    "/login",
    response_model=ApiResponse[MerchantSession],
    summary="Sign a merchant account in to the platform",
)
async def login(
    request: Request, data: MerchantLogin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[MerchantSession]:
    key = await _throttle(request, "merchant-login", data.email)
    result = await MerchantAuthService(session).login(data)
    await rate_limit.reset(key)
    return ok(result, message="Login successful")


@router.post(
    "/refresh",
    response_model=ApiResponse[MerchantSession],
    summary="Rotate a platform refresh token",
)
async def refresh(
    request: Request, data: MerchantRefresh, session: AsyncSession = Depends(get_db)
) -> ApiResponse[MerchantSession]:
    settings = get_settings()
    await rate_limit.hit(
        rate_limit.key_for("merchant-refresh", client_ip(request)),
        limit=settings.refresh_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    return ok(await MerchantAuthService(session).refresh(data.refresh_token), message="Refreshed")


@router.post("/logout", response_model=ApiResponse[None], summary="Revoke a platform refresh token")
async def logout(data: MerchantRefresh, session: AsyncSession = Depends(get_db)) -> ApiResponse[None]:
    await MerchantAuthService(session).logout(data.refresh_token)
    return ok(None, message="Signed out")


@router.get("/me", response_model=ApiResponse[MerchantAccountRead], summary="The signed-in account")
async def me(account: CurrentAccount) -> ApiResponse[MerchantAccountRead]:
    return ok(MerchantAccountRead.model_validate(account), message="Account")
