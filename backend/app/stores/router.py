"""The current brand's storefront: settings, publication and custom domains.

The brand is the one the request resolved to (a brand token's membership),
never an id in the path or body.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.brands.dependencies import BrandManager
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.stores.schemas import DomainCreate, DomainRead, StorePublish, StoreRead, StoreUpdate
from app.stores.service import StoreService, domain_read, store_read
from app.tenants.resolver import CurrentTenant

router = APIRouter(prefix="/brand", tags=["Brand Store"])


@router.get("/store", response_model=ApiResponse[StoreRead], summary="This brand's store")
async def get_store(
    tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)
) -> ApiResponse[StoreRead]:
    return ok(store_read(await StoreService(session, tenant).get()), message="Store")


@router.put("/store", response_model=ApiResponse[StoreRead], summary="Change the store's settings")
async def update_store(
    data: StoreUpdate,
    tenant: CurrentTenant,
    user: BrandManager,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[StoreRead]:
    return ok(store_read(await StoreService(session, tenant).update(data)), message="Store updated")


@router.post(
    "/store/publish", response_model=ApiResponse[StoreRead], summary="Publish or unpublish the store"
)
async def publish_store(
    data: StorePublish,
    tenant: CurrentTenant,
    user: BrandManager,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[StoreRead]:
    store = await StoreService(session, tenant).set_published(data.published)
    return ok(store_read(store), message="Store published" if data.published else "Store unpublished")


@router.get("/domains", response_model=ApiResponse[list[DomainRead]], summary="Custom domains")
async def list_domains(
    tenant: CurrentTenant, user: BrandManager, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[DomainRead]]:
    domains = await StoreService(session, tenant).list_domains()
    return ok([domain_read(d) for d in domains], message="Domains")


@router.post(
    "/domains",
    response_model=ApiResponse[DomainRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a custom domain (served once verified)",
)
async def add_domain(
    data: DomainCreate,
    tenant: CurrentTenant,
    user: BrandManager,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[DomainRead]:
    return ok(domain_read(await StoreService(session, tenant).add_domain(data)), message="Domain added")


@router.delete("/domains/{domain_id}", response_model=ApiResponse[None], summary="Remove a domain")
async def remove_domain(
    domain_id: UUID,
    tenant: CurrentTenant,
    user: BrandManager,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[None]:
    await StoreService(session, tenant).remove_domain(domain_id)
    return ok(None, message="Domain removed")
