"""Which hostnames the reverse proxy may get HTTPS certificates for.

Caddy issues certificates on demand (the first request for a new brand
subdomain or custom domain) and asks this endpoint first, so nobody can make
the server request certificates for arbitrary names (rate-limit abuse at the
certificate authority). Answers 200 or 404 only, no body worth reading.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.stores.models import Store
from app.tenants.models import Tenant, TenantDomain
from app.tenants.resolver import normalize_hostname, platform_subdomain

router = APIRouter(prefix="/internal", tags=["Internal"], include_in_schema=False)

# Platform hosts served by the proxy itself (see deploy/Caddyfile).
PLATFORM_HOSTS = ("", "app", "api", "media")


async def certificate_allowed(session: AsyncSession, hostname: str | None) -> bool:
    if not hostname:
        return False
    root = get_settings().platform_root_domain.strip().lower().strip(".")
    if hostname in {f"{label}.{root}".lstrip(".") for label in PLATFORM_HOSTS}:
        return True
    subdomain = platform_subdomain(hostname)
    if subdomain is not None:
        return bool(
            await session.scalar(
                select(
                    exists().where(
                        Store.subdomain == subdomain,
                        Store.tenant_id == Tenant.id,
                        Tenant.is_active.is_(True),
                    )
                )
            )
        )
    return bool(
        await session.scalar(
            select(
                exists().where(
                    TenantDomain.domain == hostname,
                    TenantDomain.verified_at.is_not(None),
                    TenantDomain.tenant_id == Tenant.id,
                    Tenant.is_active.is_(True),
                )
            )
        )
    )


@router.get("/tls-allowed", status_code=200)
async def tls_allowed(
    domain: str = Query(max_length=253), session: AsyncSession = Depends(get_db)
) -> Response:
    allowed = await certificate_allowed(session, normalize_hostname(domain))
    return Response(status_code=200 if allowed else 404)
