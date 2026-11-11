from __future__ import annotations

from enum import Enum


class MediaKind(str, Enum):
    """What a stored file is. Originals are never overwritten by derived files."""

    PRODUCT_ORIGINAL = "PRODUCT_ORIGINAL"  # a brand's own product photo, as uploaded
    AI_GENERATED = "AI_GENERATED"  # provider output, private until approved
    STOREFRONT = "STOREFRONT"  # approved copy of an AI image, public
    THUMBNAIL = "THUMBNAIL"  # small derivative of another asset
    VIRTUAL_MODEL = "VIRTUAL_MODEL"  # platform-owned character photo


MEDIA_KINDS = tuple(k.value for k in MediaKind)


class Visibility(str, Enum):
    PUBLIC = "PUBLIC"  # served at a stable URL
    PRIVATE = "PRIVATE"  # only through short-lived signed URLs


VISIBILITIES = tuple(v.value for v in Visibility)


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


REVIEW_STATUSES = tuple(s.value for s in ReviewStatus)
