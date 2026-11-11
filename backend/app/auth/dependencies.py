from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.auth.permissions import Permission
from app.auth.security import decode_token
from app.core.database import get_db
from app.core.error_codes import AuthErrorCode
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.tenants.models import Tenant
from app.tenants.resolver import CurrentTenant
from app.users.models import User
from app.users.repository import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def _authenticated_user(
    tenant: Tenant, token: str, session: AsyncSession
) -> User:
    payload = decode_token(token, expected_type="access")

    if payload.tenant_id != str(tenant.id):
        raise AuthenticationError(
            "Invalid authentication credentials",
            error_code=AuthErrorCode.INVALID_TOKEN,
        )

    try:
        user_id = UUID(payload.user_id)
    except ValueError as exc:
        raise AuthenticationError(
            "Invalid authentication credentials",
            error_code=AuthErrorCode.INVALID_TOKEN,
        ) from exc

    user = await UserRepository(session).get_by_id(tenant_id=tenant.id, user_id=user_id)
    if user is None or not user.is_active:
        raise AuthenticationError(
            "Invalid authentication credentials",
            error_code=AuthErrorCode.INVALID_TOKEN,
        )

    return user


async def get_current_user(
    tenant: CurrentTenant,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Not authenticated", error_code=AuthErrorCode.NOT_AUTHENTICATED)

    return await _authenticated_user(tenant, credentials.credentials, session)


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_user_optional(
    tenant: CurrentTenant,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User | None:
    """The signed-in user, or None for a guest. A token that is sent must still be valid."""
    if credentials is None or not credentials.credentials:
        return None

    return await _authenticated_user(tenant, credentials.credentials, session)


CurrentUserOptional = Annotated[User | None, Depends(get_current_user_optional)]


def _require_roles(*roles: UserRole) -> Callable[..., Coroutine[Any, Any, User]]:
    allowed = frozenset(role.value for role in roles)

    async def dependency(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise PermissionDeniedError("Insufficient permissions")
        return current_user

    return dependency


require_admin = _require_roles(UserRole.ADMIN)

require_staff = _require_roles(UserRole.ADMIN, UserRole.STAFF)

require_customer = _require_roles(UserRole.CUSTOMER)


def require_permission(
    permission: Permission, *, legacy_staff: bool = False
) -> Callable[..., Coroutine[Any, Any, User]]:
    """ADMIN always passes; STAFF needs the permission.

    `legacy_staff=True` marks an endpoint unconfigured (NULL-permission) staff
    could already use, so their existing access is kept.
    """

    async def dependency(current_user: CurrentUser) -> User:
        if current_user.role == UserRole.ADMIN.value:
            return current_user
        if current_user.role == UserRole.STAFF.value:
            granted = current_user.permissions
            if granted is None:
                if legacy_staff:
                    return current_user
            elif permission.value in granted:
                return current_user
        raise PermissionDeniedError("Insufficient permissions")

    return dependency
