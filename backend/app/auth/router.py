from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.auth.permissions import effective_permissions
from app.auth.schemas import (
    GoogleLoginPayload,
    LogoutPayload,
    PasswordLoginPayload,
    ProfileUpdate,
    RefreshPayload,
    TenantResponse,
    TokenPair,
    UserProfile,
    WidgetLoginPayload,
)
from app.auth.security import hash_refresh_token
from app.auth.service import AuthService
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.request_context import client_ip
from app.core.responses import ApiResponse, ok
from app.tenants.models import Tenant
from app.tenants.resolver import CurrentTenant
from app.users.service import AccountErasureService, UserService

router = APIRouter(prefix="/auth", tags=["Auth"])


def _profile(user) -> UserProfile:
    profile = UserProfile.model_validate(user)
    return profile.model_copy(
        update={"permissions": sorted(effective_permissions(user.role, user.permissions))}
    )
admin_router = APIRouter(prefix="/admin/auth", tags=["Admin Auth"])
staff_router = APIRouter(prefix="/staff/auth", tags=["Staff Auth"])


async def _throttle(
    request: Request,
    tenant: Tenant,
    scope: str,
    subject: str,
    *,
    limit: int,
    window_seconds: int,
) -> str:
    settings = get_settings()
    ip = client_ip(request)

    await rate_limit.hit(
        rate_limit.key_for(f"{scope}-ip", ip, str(tenant.id)),
        limit=settings.otp_ip_rate_limit_attempts,
        window_seconds=window_seconds,
    )

    subject_key = rate_limit.key_for(scope, ip, str(tenant.id), subject)
    await rate_limit.hit(subject_key, limit=limit, window_seconds=window_seconds)
    return subject_key


@router.post(
    "/widget/login",
    response_model=ApiResponse[TokenPair],
    summary="Sign a customer in from a MSG91-verified widget token",
)
async def widget_login(
    request: Request,
    data: WidgetLoginPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenPair]:
    """
    The storefront's only customer sign-in. MSG91's widget owns the code
    itself -- sending, resending, expiry and attempt limits all sit with them
    -- and hands the browser an access token once a number is verified. All
    that is left here is to confirm that token with MSG91 and turn the number
    it attests to into a session.
    """
    settings = get_settings()

    # Throttled on the token rather than a phone number, since the number is
    # not known until MSG91 has answered, and anything the caller claimed
    # before then is unverified. MSG91 rate limits the codes themselves.
    key = await _throttle(
        request,
        tenant,
        "widget-login",
        hash_refresh_token(data.access_token),
        limit=settings.otp_verify_rate_limit_attempts,
        window_seconds=settings.otp_rate_limit_window_seconds,
    )

    tokens = await AuthService(session, tenant).login_with_widget(data.access_token)

    await rate_limit.reset(key)
    return ok(tokens, message="Login successful")

@router.post(
    "/google/login",
    response_model=ApiResponse[TokenPair],
    summary="Sign a customer in with Google",
)
async def google_login(
    request: Request,
    data: GoogleLoginPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenPair]:
    settings = get_settings()
    key = await _throttle(
        request,
        tenant,
        "google-login",
        hash_refresh_token(data.credential),
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    tokens = await AuthService(session, tenant).login_with_google(data.credential)
    await rate_limit.reset(key)
    return ok(tokens, message="Login successful")

@admin_router.post(
    "/login",
    response_model=ApiResponse[TokenPair],
    summary="Verify an admin password and receive a token pair",
)
async def admin_login(
    request: Request,
    data: PasswordLoginPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenPair]:
    settings = get_settings()
    key = await _throttle(
        request,
        tenant,
        "admin-login",
        data.identifier.strip().lower(),
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )

    tokens = await AuthService(session, tenant).admin_login(
        data.identifier, data.password, request=request
    )

    await rate_limit.reset(key)
    return ok(tokens, message="Login successful")


@staff_router.post(
    "/login",
    response_model=ApiResponse[TokenPair],
    summary="Verify a staff password and receive a token pair",
)
async def staff_login(
    request: Request,
    data: PasswordLoginPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenPair]:
    settings = get_settings()
    key = await _throttle(
        request,
        tenant,
        "staff-login",
        data.identifier.strip().lower(),
        limit=settings.login_rate_limit_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )

    tokens = await AuthService(session, tenant).staff_login(
        data.identifier, data.password, request=request
    )

    await rate_limit.reset(key)
    return ok(tokens, message="Login successful")


@router.post(
    "/refresh",
    response_model=ApiResponse[TokenPair],
    summary="Rotate a refresh token for a new token pair",
)
async def refresh(
    request: Request,
    data: RefreshPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[TokenPair]:
    settings = get_settings()
    await _throttle(
        request,
        tenant,
        "refresh",
        hash_refresh_token(data.refresh_token),
        limit=settings.refresh_rate_limit_attempts,
        window_seconds=settings.otp_rate_limit_window_seconds,
    )

    tokens = await AuthService(session, tenant).refresh_tokens(data.refresh_token)
    return ok(tokens, message="Token refreshed successfully")


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke a refresh token",
)
async def logout(
    data: LogoutPayload,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> Response:
    await AuthService(session, tenant).logout(data.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/me",
    response_model=ApiResponse[UserProfile],
    summary="The authenticated user's profile",
)
async def get_me(current_user: CurrentUser) -> ApiResponse[UserProfile]:
    return ok(_profile(current_user), message="Authenticated user")


@router.patch(
    "/me",
    response_model=ApiResponse[UserProfile],
    summary="Edit your name or email",
)
async def update_me(
    data: ProfileUpdate,
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[UserProfile]:
    user = await UserService(session).update_profile(current_user, data)
    return ok(_profile(user), message="Profile updated")


@router.delete(
    "/me",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Erase your account and personal data",
)
async def delete_me(
    current_user: CurrentUser,
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Carts, wishlists, addresses and searches go. Orders stay, minus the person."""
    await AccountErasureService(session, current_user.tenant_id).erase(current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/tenant",
    response_model=ApiResponse[TenantResponse],
    summary="The storefront this request belongs to",
)
async def get_tenant(tenant: CurrentTenant) -> ApiResponse[TenantResponse]:
    return ok(TenantResponse.model_validate(tenant), message="Current tenant")
