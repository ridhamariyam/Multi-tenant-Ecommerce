"""Authorization for routes that act on the brand of the current request."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request

from app.auth.constants import UserRole
from app.auth.dependencies import CurrentUser
from app.brands.constants import BRAND_MANAGER_ROLES
from app.brands.models import BrandMember
from app.core.error_codes import BrandErrorCode
from app.core.exceptions import PermissionDeniedError
from app.tenants.resolver import CurrentTenant
from app.users.models import User


def current_membership(request: Request) -> BrandMember | None:
    """The membership a brand token resolved, or None for any other token."""
    return getattr(request.state, "brand_membership", None)


def require_brand_roles(
    roles: frozenset[str],
) -> Callable[..., Coroutine[Any, Any, User]]:
    """The signed-in brand user, if their membership has one of `roles`.

    A brand token is checked against its membership role. A per-store ADMIN
    token (the login that predates memberships) is accepted as a manager,
    so existing admins keep their access; STAFF tokens without a membership
    are not.
    """

    async def dependency(request: Request, tenant: CurrentTenant, user: CurrentUser) -> User:
        membership = current_membership(request)
        if membership is not None:
            if membership.tenant_id == tenant.id and membership.role in roles:
                return user
        elif user.role == UserRole.ADMIN.value and roles & BRAND_MANAGER_ROLES:
            return user
        raise PermissionDeniedError(
            "Your role in this brand does not allow this", error_code=BrandErrorCode.ROLE_REQUIRED
        )

    return dependency


BrandManager = Annotated[User, Depends(require_brand_roles(BRAND_MANAGER_ROLES))]
