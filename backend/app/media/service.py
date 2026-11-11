"""Store files as media assets and hand out URLs for them."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.uploads import STORAGE_DOWN, CheckedImage
from app.core.error_codes import MediaErrorCode
from app.core.exceptions import ConflictError, ServiceUnavailableError
from app.core.storage import StorageError, get_storage
from app.media.constants import MediaKind, Visibility
from app.media.models import MediaAsset

SIGNED_URL_SECONDS = 900

OBJECT_STORAGE_REQUIRED = (
    "This needs object storage. Set STORAGE_BACKEND=s3 (MinIO in development, "
    "see docs/platform-architecture.md)."
)


def require_object_storage():
    storage = get_storage()
    if not storage.supports_presigned_uploads:
        raise ConflictError(
            OBJECT_STORAGE_REQUIRED, error_code=MediaErrorCode.OBJECT_STORAGE_REQUIRED
        )
    return storage


class MediaAssetRead(BaseModel):
    id: uuid.UUID
    kind: str
    url: str
    url_expires_in: int | None  # seconds, for private assets
    content_type: str
    width: int | None
    height: int | None
    review_status: str | None
    product_id: uuid.UUID | None
    created_at: datetime


async def asset_url(asset: MediaAsset) -> str:
    if asset.visibility == Visibility.PUBLIC.value and asset.url:
        return asset.url
    try:
        return await require_object_storage().signed_url(
            asset.storage_key, expires_seconds=SIGNED_URL_SECONDS
        )
    except StorageError as exc:
        raise ServiceUnavailableError(STORAGE_DOWN) from exc


async def asset_read(asset: MediaAsset) -> MediaAssetRead:
    private = asset.visibility == Visibility.PRIVATE.value
    return MediaAssetRead(
        id=asset.id,
        kind=asset.kind,
        url=await asset_url(asset),
        url_expires_in=SIGNED_URL_SECONDS if private else None,
        content_type=asset.content_type,
        width=asset.width,
        height=asset.height,
        review_status=asset.review_status,
        product_id=asset.product_id,
        created_at=asset.created_at,
    )


async def store_asset(
    session: AsyncSession,
    *,
    data: bytes,
    image: CheckedImage,
    key: str,
    kind: MediaKind,
    visibility: Visibility,
    tenant_id: uuid.UUID | None,
    product_id: uuid.UUID | None = None,
    job_id: uuid.UUID | None = None,
    source_asset_id: uuid.UUID | None = None,
    review_status: str | None = None,
) -> MediaAsset:
    """Upload the bytes, then add (not commit) the row describing them."""
    try:
        url = await get_storage().save(data, key=key, content_type=image.content_type)
    except StorageError as exc:
        raise ServiceUnavailableError(STORAGE_DOWN) from exc
    asset = MediaAsset(
        tenant_id=tenant_id,
        kind=kind.value,
        visibility=visibility.value,
        storage_key=key,
        url=url if visibility == Visibility.PUBLIC else None,
        content_type=image.content_type,
        size_bytes=len(data),
        width=image.width,
        height=image.height,
        product_id=product_id,
        job_id=job_id,
        source_asset_id=source_asset_id,
        review_status=review_status,
    )
    session.add(asset)
    await session.flush()
    return asset
