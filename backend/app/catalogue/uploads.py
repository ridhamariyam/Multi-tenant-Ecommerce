"""Validate uploaded raster images and store their original bytes unchanged."""

from __future__ import annotations

import io
from dataclasses import dataclass
from uuid import UUID

from PIL import Image, UnidentifiedImageError

from app.core.config import get_settings
from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.storage import (
    ObjectTooLargeError,
    PresignedUpload,
    StorageError,
    get_storage,
    parse_pending_key,
    pending_key,
    upload_key,
)

ALLOWED_CONTENT_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})

FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
FORMAT_CONTENT_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

MAX_SOURCE_PIXELS = 50_000_000

UNSUPPORTED_TYPE = (
    "Upload a JPEG, PNG or WebP image. "
    f"Accepted types: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
)
NOT_AN_IMAGE = "That file is not a readable image"
TOO_MANY_PIXELS = "That image has too many pixels"
EMPTY_UPLOAD = "The uploaded file is empty"


def _too_large(limit: int) -> str:
    return f"Images must be {limit // (1024 * 1024)}MB or smaller"


def _validate_image(data: bytes) -> str:
    """Validate the image and return its detected format without altering its bytes."""
    try:
        image = Image.open(io.BytesIO(data), formats=list(FORMAT_EXTENSIONS))
        if image.width * image.height > MAX_SOURCE_PIXELS:
            raise ValidationError(TOO_MANY_PIXELS)
        image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValidationError(NOT_AN_IMAGE) from exc

    if image.format not in FORMAT_EXTENSIONS:
        raise ValidationError(UNSUPPORTED_TYPE)
    return image.format


def _check_declared(content_type: str, size: int | None, limit: int) -> None:
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(UNSUPPORTED_TYPE)
    if size is not None and size <= 0:
        raise ValidationError(EMPTY_UPLOAD)
    if size is not None and size > limit:
        raise ValidationError(_too_large(limit))


PRESIGN_UNAVAILABLE = (
    "Direct uploads need object storage (STORAGE_BACKEND=s3). "
    "Upload through /catalogue/images/upload instead."
)
UPLOAD_NOT_FOUND = "No pending upload with that id. It may have expired or already been completed."
STORAGE_DOWN = "File storage is unavailable. Try again shortly."


async def presign_image_upload(tenant_id: UUID, content_type: str, size: int) -> PresignedUpload:
    """A one-file, short-lived browser upload into this brand's pending area."""
    settings = get_settings()
    _check_declared(content_type, size, settings.max_upload_bytes)
    storage = get_storage()
    if not storage.supports_presigned_uploads:
        raise ConflictError(PRESIGN_UNAVAILABLE)
    try:
        return await storage.presign_upload(  # type: ignore[attr-defined]
            key=pending_key(tenant_id),
            content_type=content_type,
            max_bytes=settings.max_upload_bytes,
        )
    except StorageError as exc:
        raise ServiceUnavailableError(STORAGE_DOWN) from exc


async def complete_image_upload(tenant_id: UUID, upload_id: str) -> str:
    """Validate a presigned upload and publish it. Returns its serving URL.

    The file the browser sent is never trusted: it is read back, decoded, and
    only then copied to a public key. The pending object is removed either way.
    """
    settings = get_settings()
    parsed = parse_pending_key(upload_id)
    # Another brand's id answers exactly like a missing one.
    if parsed is None or parsed[0] != tenant_id:
        raise NotFoundError(UPLOAD_NOT_FOUND)
    storage = get_storage()
    if not storage.supports_presigned_uploads:
        raise ConflictError(PRESIGN_UNAVAILABLE)

    try:
        try:
            stored = await storage.read(  # type: ignore[attr-defined]
                upload_id, max_bytes=settings.max_upload_bytes
            )
        except ObjectTooLargeError as exc:
            await storage.delete(upload_id)
            raise ValidationError(_too_large(settings.max_upload_bytes)) from exc
        if stored is None:
            raise NotFoundError(UPLOAD_NOT_FOUND)

        try:
            _check_declared(stored.content_type or "", len(stored.data), settings.max_upload_bytes)
            image_format = _validate_image(stored.data)
        except ValidationError:
            await storage.delete(upload_id)
            raise

        # The final name comes from the pending token, so completing the same
        # upload twice at once writes one object, not two.
        key = f"{tenant_id}/{parsed[1]}{FORMAT_EXTENSIONS[image_format]}"
        url = await storage.save(
            stored.data, key=key, content_type=FORMAT_CONTENT_TYPES[image_format]
        )
        await storage.delete(upload_id)
        return url
    except StorageError as exc:
        raise ServiceUnavailableError(STORAGE_DOWN) from exc


@dataclass(frozen=True)
class CheckedImage:
    format: str
    extension: str
    content_type: str
    width: int
    height: int


def check_image(content_type: str, data: bytes) -> CheckedImage:
    """Every rule store_image applies, returning what the bytes really are."""
    settings = get_settings()
    _check_declared(content_type, len(data), settings.max_upload_bytes)
    image_format = _validate_image(data)
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    return CheckedImage(
        format=image_format,
        extension=FORMAT_EXTENSIONS[image_format],
        content_type=FORMAT_CONTENT_TYPES[image_format],
        width=width,
        height=height,
    )


async def store_image(tenant_id: UUID, content_type: str, data: bytes) -> str:
    """Validate and store one upload unchanged. Returns its serving URL."""
    settings = get_settings()

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(UNSUPPORTED_TYPE)

    if not data:
        raise ValidationError(EMPTY_UPLOAD)

    if len(data) > settings.max_upload_bytes:
        raise ValidationError(_too_large(settings.max_upload_bytes))

    image_format = _validate_image(data)

    key = upload_key(tenant_id, FORMAT_EXTENSIONS[image_format])
    try:
        return await get_storage().save(
            data, key=key, content_type=FORMAT_CONTENT_TYPES[image_format]
        )
    except StorageError as exc:
        raise ServiceUnavailableError(STORAGE_DOWN) from exc
