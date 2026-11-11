"""Which brand a request acts for.

Two ways in, checked in this order:

1. A brand token: an access token a merchant account obtained for one brand
   (it carries a membership id). The brand is the one the membership belongs
   to, and the membership, the account and the brand must all still be
   active, so removing a member or suspending a brand takes effect on the
   next request rather than when the token expires. Never a brand id taken
   from the request itself.
2. The hostname: a verified domain, or <subdomain>.<platform root domain>,
   of a published store. This is how storefronts and the per-store admin
   logins have always resolved.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import STAFF_ROLES
from app.auth.security import decode_token
from app.brands.constants import MemberStatus
from app.brands.models import BrandMember
from app.core.config import get_settings
from app.core.database import get_db
from app.core.error_codes import AuthErrorCode, BrandErrorCode, TenantErrorCode
from app.core.exceptions import AuthenticationError, NotFoundError, PermissionDeniedError
from app.merchants.models import MerchantAccount
from app.tenants.models import Tenant
from app.tenants.repository import TenantRepository

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]", "0.0.0.0"})


def normalize_hostname(value: str | None) -> str | None:
    if not value:
        return None

    host = value.strip().lower()
    if host.startswith("["):
        return host.partition("]")[0] + "]"

    return host.partition(":")[0].rstrip(".") or None


def request_hostname(request: Request) -> str | None:
    if get_settings().trust_forwarded_host:
        forwarded = request.headers.get("x-forwarded-host")
        if forwarded:
            return normalize_hostname(forwarded.split(",")[0])

    return normalize_hostname(request.headers.get("host"))


def platform_subdomain(hostname: str) -> str | None:
    """"cliq" for cliq.<platform root>; None for any other host."""
    root = get_settings().platform_root_domain.strip().lower().strip(".")
    suffix = f".{root}"
    if not root or not hostname.endswith(suffix):
        return None
    label = hostname[: -len(suffix)]
    return label if label and "." not in label else None


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization") or ""
    scheme, _, token = header.partition(" ")
    return token.strip() or None if scheme.lower() == "bearer" else None


_INVALID = "Invalid authentication credentials"


def _staff_token_for(request: Request, tenant: Tenant) -> bool:
    """Whether the request carries a valid ADMIN/STAFF access token for this brand.

    Only lets the request reach the brand; the route's own user dependency
    still loads and checks the user.
    """
    token = _bearer(request)
    if token is None:
        return False
    try:
        payload = decode_token(token, expected_type="access")
    except AuthenticationError:
        return False
    return payload.tenant_id == str(tenant.id) and payload.role in STAFF_ROLES


async def _brand_from_token(request: Request, session: AsyncSession) -> Tenant | None:
    token = _bearer(request)
    if token is None:
        return None
    try:
        payload = decode_token(token, expected_type="access")
    except AuthenticationError:
        # Not a brand token (or not valid at all): the user dependency, if
        # the route has one, reports it. Resolution falls back to the host.
        return None
    if not payload.membership_id:
        return None

    try:
        membership_id = UUID(payload.membership_id)
    except ValueError as exc:
        raise AuthenticationError(_INVALID, error_code=AuthErrorCode.INVALID_TOKEN) from exc

    row = (
        await session.execute(
            select(BrandMember, MerchantAccount, Tenant)
            .join(MerchantAccount, MerchantAccount.id == BrandMember.account_id)
            .join(Tenant, Tenant.id == BrandMember.tenant_id)
            .where(BrandMember.id == membership_id)
        )
    ).one_or_none()
    if row is None:
        raise AuthenticationError(_INVALID, error_code=AuthErrorCode.INVALID_TOKEN)
    membership, account, tenant = row
    if (
        membership.status != MemberStatus.ACTIVE.value
        or not account.is_active
        or str(membership.user_id) != payload.user_id
        or str(membership.tenant_id) != payload.tenant_id
    ):
        raise AuthenticationError(_INVALID, error_code=AuthErrorCode.INVALID_TOKEN)
    if not tenant.is_active:
        raise PermissionDeniedError("This brand is suspended", error_code=BrandErrorCode.SUSPENDED)

    request.state.brand_membership = membership
    request.state.merchant_account = account
    return tenant


async def resolve_tenant(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Tenant:
    cached = getattr(request.state, "tenant", None)
    if cached is not None:
        return cached

    tenant = await _brand_from_token(request, session)

    hostname = request_hostname(request)
    repository = TenantRepository(session)
    settings = get_settings()

    if tenant is None and hostname:
        found = await repository.get_active_by_domain(hostname)
        if found is None:
            subdomain = platform_subdomain(hostname)
            if subdomain:
                found = await repository.get_active_by_subdomain(subdomain)
        if found is not None:
            candidate, public = found
            # An unpublished store is hidden from the public, not from its own staff.
            if public or _staff_token_for(request, candidate):
                tenant = candidate

    if tenant is None and not settings.is_production and hostname in LOOPBACK_HOSTS:
        tenant = await repository.get_active_by_slug(settings.seed_tenant_slug)

    if tenant is None:
        raise NotFoundError(
            "Unknown storefront domain", error_code=TenantErrorCode.UNKNOWN_STOREFRONT
        )

    request.state.tenant = tenant
    return tenant


CurrentTenant = Annotated[Tenant, Depends(resolve_tenant)]


async def resolve_tenant_optional(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> Tenant | None:
    try:
        return await resolve_tenant(request, session)
    except NotFoundError:
        return None


CurrentTenantOptional = Annotated[Tenant | None, Depends(resolve_tenant_optional)]
