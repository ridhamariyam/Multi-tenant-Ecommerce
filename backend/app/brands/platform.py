"""Platform administration of brands: oversight, suspension, domain approval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brands.constants import MemberStatus
from app.brands.models import BrandMember
from app.brands.schemas import BrandRead
from app.core.database import get_db
from app.core.error_codes import BrandErrorCode, StoreErrorCode
from app.core.exceptions import NotFoundError
from app.core.pagination import PageParams
from app.core.responses import ApiResponse, ok, paginated
from app.audit.service import record_platform_action
from app.merchants.dependencies import PlatformAdmin
from app.merchants.models import MerchantAccount
from app.stores.dns_check import check_ownership
from app.stores.models import Store
from app.stores.schemas import DomainCheckRead, DomainRead, StoreRead
from app.stores.service import domain_check_read, domain_read, store_read
from app.tenants.constants import BrandStatus
from app.tenants.models import Tenant, TenantDomain

router = APIRouter(prefix="/platform/admin", tags=["Platform Admin"])


class PlatformBrandRead(BaseModel):
    brand: BrandRead
    store: StoreRead | None
    member_count: int
    suspended_at: datetime | None
    suspension_reason: str | None
    plan_code: str | None = None
    subscription_status: str | None = None


class BrandQuery(PageParams):
    search: str | None = Field(default=None, max_length=100)
    status: BrandStatus | None = None


class SuspendBrand(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


async def _brand(session: AsyncSession, brand_id: UUID) -> Tenant:
    tenant = await session.get(Tenant, brand_id)
    if tenant is None:
        raise NotFoundError("Brand not found", error_code=BrandErrorCode.NOT_FOUND)
    return tenant


async def _platform_read(session: AsyncSession, tenant: Tenant) -> PlatformBrandRead:
    store = await session.scalar(select(Store).where(Store.tenant_id == tenant.id))
    members = await session.scalar(
        select(func.count()).where(
            BrandMember.tenant_id == tenant.id, BrandMember.status == MemberStatus.ACTIVE.value
        )
    )
    from app.subscriptions.models import BrandSubscription, SubscriptionPlan

    plan = (
        await session.execute(
            select(SubscriptionPlan.code, BrandSubscription.status)
            .join(SubscriptionPlan, SubscriptionPlan.id == BrandSubscription.plan_id)
            .where(BrandSubscription.tenant_id == tenant.id)
        )
    ).first()
    return PlatformBrandRead(
        plan_code=plan.code if plan else None,
        subscription_status=plan.status if plan else None,
        brand=BrandRead.model_validate(tenant),
        store=store_read(store) if store else None,
        member_count=members or 0,
        suspended_at=tenant.suspended_at,
        suspension_reason=tenant.suspension_reason,
    )


@router.get("/brands", response_model=ApiResponse[list[PlatformBrandRead]], summary="Every brand")
async def list_brands(
    params: Annotated[BrandQuery, Query()],
    admin: PlatformAdmin,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PlatformBrandRead]]:
    query = select(Tenant)
    if params.search:
        like = f"%{params.search.strip()}%"
        query = query.where(or_(Tenant.name.ilike(like), Tenant.slug.ilike(like)))
    if params.status:
        query = query.where(Tenant.status == params.status.value)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    tenants = await session.scalars(
        query.order_by(Tenant.created_at.desc())
        .offset((params.page - 1) * params.page_size)
        .limit(params.page_size)
    )
    items = [await _platform_read(session, t) for t in tenants]
    return paginated(items, total_items=total or 0, params=params, message="Brands")


@router.post(
    "/brands/{brand_id}/suspend", response_model=ApiResponse[PlatformBrandRead], summary="Suspend a brand"
)
async def suspend_brand(
    brand_id: UUID,
    data: SuspendBrand,
    admin: PlatformAdmin,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[PlatformBrandRead]:
    tenant = await _brand(session, brand_id)
    tenant.status = BrandStatus.SUSPENDED.value
    tenant.is_active = False
    tenant.suspended_at = datetime.now(timezone.utc)
    tenant.suspension_reason = data.reason
    await record_platform_action(
        session, tenant.id, admin.email, "brand.suspended", "brand", tenant.id,
        summary=f"Suspended: {data.reason}", request=request,
    )
    await session.commit()
    await session.refresh(tenant)
    return ok(await _platform_read(session, tenant), message="Brand suspended")


@router.post(
    "/brands/{brand_id}/activate", response_model=ApiResponse[PlatformBrandRead], summary="Reinstate a brand"
)
async def activate_brand(
    brand_id: UUID, admin: PlatformAdmin, request: Request, session: AsyncSession = Depends(get_db)
) -> ApiResponse[PlatformBrandRead]:
    tenant = await _brand(session, brand_id)
    tenant.status = BrandStatus.ACTIVE.value
    tenant.is_active = True
    tenant.suspended_at = None
    tenant.suspension_reason = None
    await record_platform_action(
        session, tenant.id, admin.email, "brand.reinstated", "brand", tenant.id,
        summary="Reinstated", request=request,
    )
    await session.commit()
    await session.refresh(tenant)
    return ok(await _platform_read(session, tenant), message="Brand reinstated")


@router.post(
    "/domains/{domain_id}/verify",
    response_model=ApiResponse[DomainRead],
    summary="Mark a custom domain verified so it starts serving",
)
async def verify_domain(
    domain_id: UUID, admin: PlatformAdmin, request: Request, session: AsyncSession = Depends(get_db)
) -> ApiResponse[DomainRead]:
    domain = await _domain(session, domain_id)
    if domain.verified_at is None:
        domain.verified_at = datetime.now(timezone.utc)
        await record_platform_action(
            session, domain.tenant_id, admin.email, "domain.verified", "domain", domain.id,
            summary=f"Verified {domain.domain} by hand", request=request,
        )
    await session.commit()
    await session.refresh(domain)
    return ok(domain_read(domain), message="Domain verified")


async def _domain(session: AsyncSession, domain_id: UUID) -> TenantDomain:
    domain = await session.get(TenantDomain, domain_id)
    if domain is None:
        raise NotFoundError("Domain not found", error_code=StoreErrorCode.DOMAIN_NOT_FOUND)
    return domain


class PlatformDomainRead(BaseModel):
    domain: DomainRead
    brand_id: UUID
    brand_name: str
    store_subdomain: str | None


class DomainQuery(PageParams):
    status: Literal["pending", "verified"] | None = None
    search: str | None = Field(default=None, max_length=100)


@router.get(
    "/domains",
    response_model=ApiResponse[list[PlatformDomainRead]],
    summary="Custom domains across brands (pending first)",
)
async def list_domains(
    params: Annotated[DomainQuery, Query()],
    admin: PlatformAdmin,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[PlatformDomainRead]]:
    query = (
        select(TenantDomain, Tenant.name, Store.subdomain)
        .join(Tenant, Tenant.id == TenantDomain.tenant_id)
        .outerjoin(Store, Store.tenant_id == TenantDomain.tenant_id)
    )
    if params.status == "pending":
        query = query.where(TenantDomain.verified_at.is_(None))
    elif params.status == "verified":
        query = query.where(TenantDomain.verified_at.is_not(None))
    if params.search:
        like = f"%{params.search.strip().lower()}%"
        query = query.where(or_(TenantDomain.domain.ilike(like), Tenant.name.ilike(like)))
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = (
        await session.execute(
            query.order_by(TenantDomain.verified_at.is_not(None), TenantDomain.created_at.desc())
            .offset((params.page - 1) * params.page_size)
            .limit(params.page_size)
        )
    ).all()
    items = [
        PlatformDomainRead(
            domain=domain_read(domain), brand_id=domain.tenant_id, brand_name=name, store_subdomain=subdomain
        )
        for domain, name, subdomain in rows
    ]
    return paginated(items, total_items=total or 0, params=params, message="Domains")


@router.post(
    "/domains/{domain_id}/check",
    response_model=ApiResponse[DomainCheckRead],
    summary="Look up a domain's TXT record; a match verifies it",
)
async def check_domain(
    domain_id: UUID, admin: PlatformAdmin, request: Request, session: AsyncSession = Depends(get_db)
) -> ApiResponse[DomainCheckRead]:
    domain = await _domain(session, domain_id)
    result = await check_ownership(domain.domain, domain.verification_token)
    if result.verified and domain.verified_at is None:
        domain.verified_at = datetime.now(timezone.utc)
        await record_platform_action(
            session, domain.tenant_id, admin.email, "domain.verified", "domain", domain.id,
            summary=f"Verified {domain.domain} by DNS", request=request,
        )
        await session.commit()
        await session.refresh(domain)
    return ok(domain_check_read(domain, result), message="Domain verified" if result.verified else "Not verified")


class PlatformOverview(BaseModel):
    brands_total: int
    brands_active: int
    brands_suspended: int
    stores_published: int
    domains_pending: int
    merchant_accounts: int


@router.get("/overview", response_model=ApiResponse[PlatformOverview], summary="Platform totals")
async def overview(admin: PlatformAdmin, session: AsyncSession = Depends(get_db)) -> ApiResponse[PlatformOverview]:
    """Counts only. Brands' business data (orders, customers) is not exposed here."""
    by_status = dict(
        (await session.execute(select(Tenant.status, func.count()).group_by(Tenant.status))).all()
    )
    published = await session.scalar(
        select(func.count()).select_from(Store).where(Store.published.is_(True))
    )
    pending = await session.scalar(
        select(func.count()).select_from(TenantDomain).where(TenantDomain.verified_at.is_(None))
    )
    accounts = await session.scalar(select(func.count()).select_from(MerchantAccount))
    return ok(
        PlatformOverview(
            brands_total=sum(by_status.values()),
            brands_active=by_status.get(BrandStatus.ACTIVE.value, 0),
            brands_suspended=by_status.get(BrandStatus.SUSPENDED.value, 0),
            stores_published=published or 0,
            domains_pending=pending or 0,
            merchant_accounts=accounts or 0,
        ),
        message="Platform overview",
    )
