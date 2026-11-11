from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.pagination import PageParams
from app.core.schemas import PartialUpdate, StrictModel
from app.ratings.constants import (
    MAX_ALT_TEXT_LENGTH,
    MAX_COMMENT_LENGTH,
    MAX_IMAGE_URL_LENGTH,
    MAX_IMAGES_PER_REVIEW,
    MAX_RATING,
    MAX_TITLE_LENGTH,
    MIN_RATING,
)


class ReviewImageCreate(StrictModel):
    image_url: str = Field(max_length=MAX_IMAGE_URL_LENGTH)
    alt_text: str | None = Field(default=None, max_length=MAX_ALT_TEXT_LENGTH)


class ReviewImageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    image_url: str
    alt_text: str | None = None
    created_at: datetime


class ReviewCreate(StrictModel):
    product_id: uuid.UUID
    rating: int = Field(ge=MIN_RATING, le=MAX_RATING)
    title: str | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)
    images: list[ReviewImageCreate] = Field(
        default_factory=list, max_length=MAX_IMAGES_PER_REVIEW
    )


class ReviewUpdate(PartialUpdate):
    """What an author may change. Approval is a moderator's call, not theirs."""

    rating: int | None = Field(default=None, ge=MIN_RATING, le=MAX_RATING)
    title: str | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    comment: str | None = Field(default=None, max_length=MAX_COMMENT_LENGTH)


class ReviewModerate(StrictModel):
    is_approved: bool


class ReviewModerationQuery(PageParams):
    """The moderation listing filter, on top of the usual page controls."""

    is_approved: bool | None = Field(
        default=None, description="Filter by approval state"
    )


class ReviewRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    product_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    rating: int
    title: str | None = None
    comment: str | None = None
    is_verified_purchase: bool
    is_approved: bool
    created_at: datetime
    images: list[ReviewImageRead] = Field(default_factory=list)


class RatingSummaryRead(BaseModel):
    product_id: uuid.UUID
    average_rating: float
    total_reviews: int
    rating_distribution: dict[int, int]


class PendingReviewRead(BaseModel):
    """A delivered product the customer has not reviewed yet."""

    order_id: uuid.UUID
    order_number: str
    product_id: uuid.UUID
    product_name: str
    variant_name: str


class ReviewRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    order_id: uuid.UUID
    customer_id: uuid.UUID
    status: str
    send_after: datetime
    sent_at: datetime | None = None
    created_at: datetime


class ReviewRequestQuery(PageParams):
    status: str | None = Field(
        default=None, pattern="^(PENDING|SENT|COMPLETED|CANCELLED)$"
    )


class ReviewRequestDispatchRead(BaseModel):
    sent: int
    completed: int
