"""Platform administration of brands: oversight, suspension, domain approval."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
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
from app.merchants.dependencies import PlatformAdmin
from app.stores.models import Store
from app.stores.schemas import DomainRead, StoreRead
from app.stores.service import domain_read, store_read
from app.tenants.constants import BrandStatus
from app.tenants.models import Tenant, TenantDomain

router = APIRouter(prefix="/platform/admin", tags=["Platform Admin"])


class PlatformBrandRead(BaseModel):
    brand: BrandRead
    store: StoreRead | None
    member_count: int


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
    return PlatformBrandRead(
        brand=BrandRead.model_validate(tenant),
        store=store_read(store) if store else None,
        member_count=members or 0,
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
    brand_id: UUID, data: SuspendBrand, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[PlatformBrandRead]:
    tenant = await _brand(session, brand_id)
    tenant.status = BrandStatus.SUSPENDED.value
    tenant.is_active = False
    tenant.suspended_at = datetime.now(timezone.utc)
    tenant.suspension_reason = data.reason
    await session.commit()
    await session.refresh(tenant)
    return ok(await _platform_read(session, tenant), message="Brand suspended")


@router.post(
    "/brands/{brand_id}/activate", response_model=ApiResponse[PlatformBrandRead], summary="Reinstate a brand"
)
async def activate_brand(
    brand_id: UUID, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[PlatformBrandRead]:
    tenant = await _brand(session, brand_id)
    tenant.status = BrandStatus.ACTIVE.value
    tenant.is_active = True
    tenant.suspended_at = None
    tenant.suspension_reason = None
    await session.commit()
    await session.refresh(tenant)
    return ok(await _platform_read(session, tenant), message="Brand reinstated")


@router.post(
    "/domains/{domain_id}/verify",
    response_model=ApiResponse[DomainRead],
    summary="Mark a custom domain verified so it starts serving",
)
async def verify_domain(
    domain_id: UUID, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[DomainRead]:
    domain = await session.get(TenantDomain, domain_id)
    if domain is None:
        raise NotFoundError("Domain not found", error_code=StoreErrorCode.DOMAIN_NOT_FOUND)
    domain.verified_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(domain)
    return ok(domain_read(domain), message="Domain verified")
