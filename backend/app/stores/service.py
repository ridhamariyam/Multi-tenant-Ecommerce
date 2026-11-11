"""A brand's storefront configuration, publication and custom domains.

Every method acts on the brand the service was built for; that brand comes
from the resolved tenant, never from the request body.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import null, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.error_codes import StoreErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.stores.constants import RESERVED_SUBDOMAINS
from app.stores.dns_check import DnsCheck, check_ownership
from app.stores.models import Store
from app.stores.schemas import DomainCheckRead, DomainCreate, DomainRead, StoreRead, StoreUpdate
from app.tenants.models import Tenant, TenantDomain


def store_url(store: Store) -> str:
    settings = get_settings()
    return settings.storefront_url_template.format(
        subdomain=store.subdomain, root=settings.platform_root_domain
    )


def store_read(store: Store) -> StoreRead:
    return StoreRead(
        id=store.id,
        name=store.name,
        subdomain=store.subdomain,
        url=store_url(store),
        theme=store.theme,
        logo_url=store.logo_url,
        favicon_url=store.favicon_url,
        primary_color=store.primary_color,
        secondary_color=store.secondary_color,
        published=store.published,
        published_at=store.published_at,
    )


def domain_check_read(domain: TenantDomain, result: DnsCheck) -> DomainCheckRead:
    return DomainCheckRead(
        domain=domain_read(domain),
        verified=result.verified,
        record_name=result.record_name,
        expected=result.expected,
        found=result.found,
        problem=result.problem,
    )


def domain_read(domain: TenantDomain) -> DomainRead:
    record = (
        f"cliq-verify={domain.verification_token}"
        if domain.verified_at is None and domain.verification_token
        else None
    )
    return DomainRead(
        id=domain.id,
        domain=domain.domain,
        is_primary=domain.is_primary,
        verified_at=domain.verified_at,
        verification_record=record,
        created_at=domain.created_at,
    )


async def check_subdomain_available(
    session: AsyncSession, subdomain: str, *, tenant_id: UUID | None = None
) -> None:
    if subdomain in RESERVED_SUBDOMAINS:
        raise ValidationError(
            "That address is reserved", error_code=StoreErrorCode.SUBDOMAIN_RESERVED
        )
    query = select(Store.id).where(Store.subdomain == subdomain)
    if tenant_id is not None:
        query = query.where(Store.tenant_id != tenant_id)
    if await session.scalar(query) is not None:
        raise ConflictError("That address is taken", error_code=StoreErrorCode.SUBDOMAIN_TAKEN)


class StoreService:
    def __init__(self, session: AsyncSession, tenant: Tenant) -> None:
        self.session = session
        self.tenant = tenant

    async def get(self) -> Store:
        store = await self.session.scalar(select(Store).where(Store.tenant_id == self.tenant.id))
        if store is None:
            raise NotFoundError("This brand has no store yet", error_code=StoreErrorCode.NOT_FOUND)
        return store

    async def update(self, data: StoreUpdate) -> Store:
        store = await self.get()
        changes = data.model_dump(exclude_unset=True)
        if "subdomain" in changes and changes["subdomain"] != store.subdomain:
            await check_subdomain_available(
                self.session, changes["subdomain"], tenant_id=self.tenant.id
            )
        for field, value in changes.items():
            setattr(store, field, value)
        await self._commit_unique()
        await self.session.refresh(store)
        return store

    async def set_published(self, published: bool) -> Store:
        store = await self.get()
        store.published = published
        # published_at keeps the first publication date across unpublishing.
        if published and store.published_at is None:
            store.published_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(store)
        return store

    async def list_domains(self) -> list[TenantDomain]:
        return list(
            await self.session.scalars(
                select(TenantDomain)
                .where(TenantDomain.tenant_id == self.tenant.id)
                .order_by(TenantDomain.created_at)
            )
        )

    async def add_domain(self, data: DomainCreate) -> TenantDomain:
        from app.subscriptions.service import SubscriptionService

        await SubscriptionService(self.session, self.tenant.id).require_feature("custom_domains")
        root = get_settings().platform_root_domain.lower()
        if data.domain == root or data.domain.endswith(f".{root}"):
            raise ValidationError(
                "Platform addresses are set with the store's subdomain",
                error_code=StoreErrorCode.DOMAIN_INVALID,
            )
        if await self.session.scalar(
            select(TenantDomain.id).where(TenantDomain.domain == data.domain)
        ) is not None:
            raise ConflictError("That domain is already in use", error_code=StoreErrorCode.DOMAIN_TAKEN)

        if data.is_primary:
            for existing in await self.list_domains():
                existing.is_primary = False
            await self.session.flush()
        domain = TenantDomain(
            tenant_id=self.tenant.id,
            domain=data.domain,
            is_primary=data.is_primary,
            # Not served until ownership is proven (see DomainRead.verification_record).
            # null() writes NULL explicitly; None would let the column default fire.
            verified_at=null(),
            verification_token=secrets.token_hex(16),
        )
        self.session.add(domain)
        await self._commit_unique(StoreErrorCode.DOMAIN_TAKEN, "That domain is already in use")
        await self.session.refresh(domain)
        return domain

    async def check_domain(self, domain_id: UUID) -> tuple[TenantDomain, DnsCheck, bool]:
        """Look up the TXT record; a match verifies the domain (it then starts serving).

        Returns the domain, the lookup, and whether this check is what verified it.
        """
        domain = await self.session.scalar(
            select(TenantDomain).where(
                TenantDomain.id == domain_id, TenantDomain.tenant_id == self.tenant.id
            )
        )
        if domain is None:
            raise NotFoundError("Domain not found", error_code=StoreErrorCode.DOMAIN_NOT_FOUND)
        if domain.verified_at is not None:
            return domain, DnsCheck(True, f"_cliq-verify.{domain.domain}", "", []), False
        result = await check_ownership(domain.domain, domain.verification_token)
        if result.verified:
            domain.verified_at = datetime.now(timezone.utc)
            await self.session.commit()
            await self.session.refresh(domain)
        return domain, result, result.verified

    async def remove_domain(self, domain_id: UUID) -> None:
        domain = await self.session.scalar(
            select(TenantDomain).where(
                TenantDomain.id == domain_id, TenantDomain.tenant_id == self.tenant.id
            )
        )
        if domain is None:
            raise NotFoundError("Domain not found", error_code=StoreErrorCode.DOMAIN_NOT_FOUND)
        await self.session.delete(domain)
        await self.session.commit()

    async def _commit_unique(
        self,
        code: StoreErrorCode = StoreErrorCode.SUBDOMAIN_TAKEN,
        message: str = "That address is taken",
    ) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(message, error_code=code) from exc
