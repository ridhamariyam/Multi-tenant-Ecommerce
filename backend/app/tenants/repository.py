from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.stores.models import Store
from app.tenants.models import Tenant, TenantDomain


class TenantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_active_by_slug(self, slug: str) -> Tenant | None:
        return await self.session.scalar(
            select(Tenant).where(Tenant.slug == slug, Tenant.is_active.is_(True))
        )

    async def get_active_by_domain(self, domain: str) -> tuple[Tenant, bool] | None:
        """The live brand a verified domain serves, and whether its store is public.

        A brand without a store row predates the platform and has always been public.
        """
        row = (
            await self.session.execute(
                select(Tenant, Store.published)
                .join(TenantDomain, TenantDomain.tenant_id == Tenant.id)
                .outerjoin(Store, Store.tenant_id == Tenant.id)
                .where(
                    TenantDomain.domain == domain,
                    TenantDomain.verified_at.is_not(None),
                    Tenant.is_active.is_(True),
                )
            )
        ).one_or_none()
        if row is None:
            return None
        tenant, published = row
        return tenant, published is not False

    async def get_active_by_subdomain(self, subdomain: str) -> tuple[Tenant, bool] | None:
        """The live brand at <subdomain>.<platform root>, and whether it is public."""
        row = (
            await self.session.execute(
                select(Tenant, Store.published)
                .join(Store, Store.tenant_id == Tenant.id)
                .where(Store.subdomain == subdomain, Tenant.is_active.is_(True))
            )
        ).one_or_none()
        return (row[0], bool(row[1])) if row else None
