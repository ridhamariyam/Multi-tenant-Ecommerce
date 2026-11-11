"""Lookbooks: a brand's styled photo with its products pinned on it.

Console: create a look, set its cover (an image uploaded to this store), pin
up to six products at points on the image, publish. Storefront: the
published looks, which the runway home shows.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.catalogue.models import Product
from app.catalogue.uploads import check_image
from app.core.database import get_db
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.responses import ApiResponse, ok
from app.core.slugs import slugify
from app.core.storage import get_storage
from app.looks.models import Look, LookItem
from app.media.constants import MediaKind, Visibility
from app.media.models import MediaAsset
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/looks", tags=["Admin-Looks"], dependencies=AUDITED)
public_router = APIRouter(prefix="/storefront/looks", tags=["Storefront-Looks"])

CanView = Depends(require_permission(Permission.CATALOGUE_VIEW, legacy_staff=True))
CanEdit = Depends(require_permission(Permission.CATALOGUE_MANAGE, legacy_staff=True))
MAX_PINS = 6


class Pin(BaseModel):
    product_id: UUID
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class LookWrite(BaseModel):
    title: str = Field(min_length=1, max_length=150)
    description: str | None = Field(default=None, max_length=2000)
    cover_url: str | None = Field(default=None, max_length=2048)
    pins: list[Pin] = Field(default_factory=list, max_length=MAX_PINS)


class PinRead(BaseModel):
    product_id: UUID
    product_name: str
    product_slug: str
    x: float
    y: float


class LookRead(BaseModel):
    id: UUID
    title: str
    slug: str
    description: str | None
    cover_url: str | None
    status: str
    pins: list[PinRead]
    published_at: datetime | None


async def _read(session: AsyncSession, look: Look) -> LookRead:
    cover = await session.get(MediaAsset, look.cover_asset_id) if look.cover_asset_id else None
    rows = (
        await session.execute(
            select(LookItem, Product.name, Product.slug)
            .join(Product, (Product.id == LookItem.product_id) & (Product.tenant_id == LookItem.tenant_id))
            .where(LookItem.tenant_id == look.tenant_id, LookItem.look_id == look.id)
            .order_by(LookItem.position)
        )
    ).all()
    return LookRead(
        id=look.id, title=look.title, slug=look.slug, description=look.description,
        cover_url=cover.url if cover else None, status=look.status, published_at=look.published_at,
        pins=[PinRead(product_id=i.product_id, product_name=n, product_slug=s, x=float(i.hotspot_x), y=float(i.hotspot_y)) for i, n, s in rows],
    )  # fmt: skip


async def _cover_asset(session: AsyncSession, tenant_id: UUID, url: str) -> UUID:
    """The cover must be an image uploaded to this store's storage."""
    existing = await session.scalar(
        select(MediaAsset.id).where(MediaAsset.tenant_id == tenant_id, MediaAsset.url == url, MediaAsset.visibility == "PUBLIC")
    )
    if existing:
        return existing
    storage = get_storage()
    key = storage.key_for_url(url)  # type: ignore[attr-defined]
    if not key or not key.startswith(f"{tenant_id}/"):
        raise ValidationError("Upload the cover image to this store first.", details=[{"field": "cover_url", "message": "Not an uploaded image"}])
    stored = await storage.read(key, max_bytes=20 * 1024 * 1024)
    if stored is None:
        raise ValidationError("That image is no longer in storage.", details=[{"field": "cover_url", "message": "Missing"}])
    image = check_image(stored.content_type or "image/jpeg", stored.data)
    asset = MediaAsset(
        tenant_id=tenant_id, kind=MediaKind.STOREFRONT.value, visibility=Visibility.PUBLIC.value, storage_key=key, url=url,
        content_type=image.content_type, size_bytes=len(stored.data), width=image.width, height=image.height,
    )  # fmt: skip
    session.add(asset)
    await session.flush()
    return asset.id


async def _look(session: AsyncSession, tenant_id: UUID, look_id: UUID) -> Look:
    look = await session.scalar(select(Look).where(Look.tenant_id == tenant_id, Look.id == look_id))
    if look is None:
        raise NotFoundError("Look not found")
    return look


async def _apply(session: AsyncSession, look: Look, data: LookWrite) -> None:
    look.title, look.description = data.title.strip(), data.description
    look.cover_asset_id = await _cover_asset(session, look.tenant_id, data.cover_url) if data.cover_url else None
    ids = [p.product_id for p in data.pins]
    if len(set(ids)) != len(ids):
        raise ValidationError("Each product can be pinned once per look.")
    found = set((await session.scalars(select(Product.id).where(Product.tenant_id == look.tenant_id, Product.id.in_(ids)))).all())
    if found != set(ids):
        raise ValidationError("Pin only this store's products.", details=[{"field": "pins", "message": "Unknown product"}])
    await session.execute(delete(LookItem).where(LookItem.tenant_id == look.tenant_id, LookItem.look_id == look.id))
    for position, pin in enumerate(data.pins):
        session.add(LookItem(tenant_id=look.tenant_id, look_id=look.id, product_id=pin.product_id, position=position, hotspot_x=pin.x, hotspot_y=pin.y))
    if look.status == "PUBLISHED" and (look.cover_asset_id is None or not data.pins):
        look.status, look.published_at = "DRAFT", None


@router.get("", response_model=ApiResponse[list[LookRead]], summary="This store's looks")
async def list_looks(tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    looks = (await session.scalars(select(Look).where(Look.tenant_id == user.tenant_id, Look.status != "ARCHIVED").order_by(Look.sort_order, Look.created_at))).all()
    return ok([await _read(session, look) for look in looks], message="Looks")


@router.post("", response_model=ApiResponse[LookRead], status_code=201, summary="Create a look")
async def create_look(data: LookWrite, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanEdit):
    base = slugify(data.title, 150, "look")
    slug, n = base, 1
    while await session.scalar(select(Look.id).where(Look.tenant_id == user.tenant_id, Look.slug == slug)):
        n += 1
        slug = f"{base}-{n}"
    look = Look(tenant_id=user.tenant_id, title=data.title, slug=slug, status="DRAFT")
    session.add(look)
    await session.flush()
    await _apply(session, look, data)
    await session.commit()
    return ok(await _read(session, look), message="Look created")


@router.put("/{look_id}", response_model=ApiResponse[LookRead], summary="Edit a look")
async def update_look(look_id: UUID, data: LookWrite, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanEdit):
    look = await _look(session, user.tenant_id, look_id)
    await _apply(session, look, data)
    await session.commit()
    return ok(await _read(session, look), message="Look saved")


class Publish(BaseModel):
    published: bool


@router.post("/{look_id}/publish", response_model=ApiResponse[LookRead], summary="Show or hide a look on the store")
async def publish_look(look_id: UUID, data: Publish, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanEdit):
    look = await _look(session, user.tenant_id, look_id)
    if data.published:
        pins = await session.scalar(select(LookItem.id).where(LookItem.tenant_id == look.tenant_id, LookItem.look_id == look.id))
        if look.cover_asset_id is None or pins is None:
            raise ConflictError("Add a cover image and at least one product before publishing.")
        look.status, look.published_at = "PUBLISHED", datetime.now(timezone.utc)
    else:
        look.status, look.published_at = "DRAFT", None
    await session.commit()
    return ok(await _read(session, look), message="Published" if data.published else "Hidden")


@router.delete("/{look_id}", response_model=ApiResponse[None], summary="Archive a look")
async def archive_look(look_id: UUID, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanEdit):
    look = await _look(session, user.tenant_id, look_id)
    look.status, look.published_at = "ARCHIVED", None
    await session.commit()
    return ok(None, message="Archived")


@public_router.get("", response_model=ApiResponse[list[LookRead]], summary="Published looks")
async def published_looks(tenant: CurrentTenant, session: AsyncSession = Depends(get_db)):
    looks = (await session.scalars(select(Look).where(Look.tenant_id == tenant.id, Look.status == "PUBLISHED").order_by(Look.sort_order, Look.published_at.desc()).limit(12))).all()
    return ok([await _read(session, look) for look in looks], message="Looks")
