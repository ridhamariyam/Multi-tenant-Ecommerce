"""Public: which brand and store a storefront host belongs to.

The frontend calls this first on every host to learn the brand's name, logo,
colours and theme. The brand comes from the hostname (or, for a brand's own
staff previewing an unpublished store, their token), never from a parameter.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.stores.service import StoreService, store_url
from app.tenants.resolver import CurrentTenant

router = APIRouter(prefix="/storefront", tags=["Storefront-Store"])


class StorefrontBrandRead(BaseModel):
    name: str
    slug: str
    description: str | None
    logo_url: str | None
    currency: str


class StorefrontStoreRead(BaseModel):
    name: str
    subdomain: str
    url: str
    theme: str
    logo_url: str | None
    favicon_url: str | None
    primary_color: str | None
    secondary_color: str | None


class StorefrontResolveRead(BaseModel):
    brand: StorefrontBrandRead
    store: StorefrontStoreRead
    preview: bool  # True when the store is unpublished and a staff member is viewing it


@router.get(
    "/resolve",
    response_model=ApiResponse[StorefrontResolveRead],
    summary="The brand and store this storefront host serves",
)
async def resolve_storefront(
    tenant: CurrentTenant, response: Response, session: AsyncSession = Depends(get_db)
) -> ApiResponse[StorefrontResolveRead]:
    store = await StoreService(session, tenant).get()
    # Theme changes should show within a minute; previews are never cached.
    response.headers["Cache-Control"] = (
        "private, no-store" if not store.published else "public, max-age=60"
    )
    response.headers["Vary"] = "Host, Authorization"
    return ok(
        StorefrontResolveRead(
            brand=StorefrontBrandRead(
                name=tenant.name,
                slug=tenant.slug,
                description=tenant.description,
                logo_url=tenant.logo_url,
                currency=tenant.currency,
            ),
            store=StorefrontStoreRead(
                name=store.name,
                subdomain=store.subdomain,
                url=store_url(store),
                theme=store.theme,
                logo_url=store.logo_url or tenant.logo_url,
                favicon_url=store.favicon_url,
                primary_color=store.primary_color,
                secondary_color=store.secondary_color,
            ),
            preview=not store.published,
        ),
        message="Storefront",
    )
