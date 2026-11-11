from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_customer, require_permission
from app.auth.permissions import Permission
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.pagination import PageParams
from app.core.responses import ApiResponse, ok, paginated
from app.ratings.constants import MAX_ALT_TEXT_LENGTH
from app.ratings.models import ReviewRequestStatus
from app.ratings.schemas import (
    PendingReviewRead,
    RatingSummaryRead,
    ReviewCreate,
    ReviewModerate,
    ReviewModerationQuery,
    ReviewRead,
    ReviewRequestDispatchRead,
    ReviewRequestQuery,
    ReviewRequestRead,
    ReviewUpdate,
)
from app.ratings.service import ReviewRequestService, ReviewService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/reviews", tags=["Ratings & Reviews"])

admin_router = APIRouter(
    prefix="/admin/reviews", tags=["Admin-Review_moderation"], dependencies=AUDITED
)


@router.post(
    "",
    response_model=ApiResponse[ReviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Review a delivered product",
)
async def create_review(
    data: ReviewCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[ReviewRead]:
    settings = get_settings()
    await rate_limit.enforce(
        "review-create",
        str(user.tenant_id),
        str(user.id),
        limit=settings.review_rate_limit_attempts,
        window_seconds=settings.commerce_rate_limit_window_seconds,
    )

    review = await ReviewService(session, user.tenant_id).create(user.id, data)
    return ok(ReviewRead.model_validate(review), message="Review created")


@router.get(
    "/pending",
    response_model=ApiResponse[list[PendingReviewRead]],
    summary="Delivered products you have not reviewed yet",
)
async def list_pending_reviews(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[list[PendingReviewRead]]:
    pending = await ReviewRequestService(session, user.tenant_id).pending_for_customer(user.id)
    return ok(
        [
            PendingReviewRead(
                order_id=order.id,
                order_number=order.order_number,
                product_id=item.product_id,
                product_name=item.product_name,
                variant_name=item.variant_name,
            )
            for order, item in pending
        ],
        message="Pending reviews retrieved",
    )


@router.post(
    "/{review_id}/images/upload",
    response_model=ApiResponse[ReviewRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a photo to your review (JPEG, PNG or WebP)",
)
async def upload_review_image(
    review_id: UUID,
    file: UploadFile = File(description="JPEG, PNG or WebP"),
    alt_text: str | None = Form(default=None, max_length=MAX_ALT_TEXT_LENGTH),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[ReviewRead]:
    # Read at most one byte past the limit, as the catalogue upload does:
    # store_image rejects anything larger, and an oversized body is never
    # pulled into memory in full.
    data = await file.read(get_settings().max_upload_bytes + 1)
    review = await ReviewService(session, user.tenant_id).add_uploaded_image(
        review_id,
        user.id,
        filename=file.filename or "",
        content_type=file.content_type or "",
        data=data,
        alt_text=alt_text,
    )
    return ok(ReviewRead.model_validate(review), message="Photo added")


@router.delete(
    "/{review_id}/images/{image_id}",
    response_model=ApiResponse[ReviewRead],
    summary="Remove a photo from your review",
)
async def delete_review_image(
    review_id: UUID,
    image_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[ReviewRead]:
    review = await ReviewService(session, user.tenant_id).delete_image(
        review_id, image_id, user.id
    )
    return ok(ReviewRead.model_validate(review), message="Photo removed")


@router.get(
    "/product/{product_id}",
    response_model=ApiResponse[list[ReviewRead]],
    summary="List approved reviews for a product",
)
async def list_product_reviews(
    product_id: UUID,
    tenant: CurrentTenant,
    params: Annotated[PageParams, Query()],
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[list[ReviewRead]]:
    reviews, total = await ReviewService(session, tenant.id).list_for_product(
        product_id, params
    )
    return paginated(
        [ReviewRead.model_validate(review) for review in reviews],
        total_items=total,
        params=params,
        message="Reviews retrieved",
    )


@router.get(
    "/product/{product_id}/summary",
    response_model=ApiResponse[RatingSummaryRead],
    summary="Average rating and star distribution for a product",
)
async def get_product_rating_summary(
    product_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[RatingSummaryRead]:
    summary = await ReviewService(session, tenant.id).summary(product_id)
    return ok(summary, message="Rating summary retrieved")


@router.patch(
    "/{review_id}",
    response_model=ApiResponse[ReviewRead],
    summary="Edit your own review",
)
async def update_review(
    review_id: UUID,
    data: ReviewUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[ReviewRead]:
    review = await ReviewService(session, user.tenant_id).update(review_id, user.id, data)
    return ok(ReviewRead.model_validate(review), message="Review updated")


@router.delete(
    "/{review_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete your own review",
)
async def delete_review(
    review_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> Response:
    await ReviewService(session, user.tenant_id).delete(review_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@admin_router.get(
    "",
    response_model=ApiResponse[list[ReviewRead]],
    summary="List reviews for moderation",
)
async def list_reviews_for_moderation(
    params: Annotated[ReviewModerationQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_VIEW)),
) -> ApiResponse[list[ReviewRead]]:
    reviews, total = await ReviewService(session, user.tenant_id).list_for_moderation(
        params, is_approved=params.is_approved
    )
    return paginated(
        [ReviewRead.model_validate(review) for review in reviews],
        total_items=total,
        params=params,
        message="Reviews retrieved",
    )


@admin_router.get(
    "/requests",
    response_model=ApiResponse[list[ReviewRequestRead]],
    summary="Automatic review requests and their state",
)
async def list_review_requests(
    params: Annotated[ReviewRequestQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[ReviewRequestRead]]:
    requests, total = await ReviewRequestService(session, user.tenant_id).list(
        params, status=ReviewRequestStatus(params.status) if params.status else None
    )
    return paginated(
        [ReviewRequestRead.model_validate(r) for r in requests],
        total_items=total,
        params=params,
        message="Review requests retrieved",
    )


@admin_router.post(
    "/requests/dispatch",
    response_model=ApiResponse[ReviewRequestDispatchRead],
    summary="Send every review request that is due now",
)
async def dispatch_review_requests(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_MANAGE)),
) -> ApiResponse[ReviewRequestDispatchRead]:
    result = await ReviewRequestService(session, user.tenant_id).dispatch_due()
    return ok(ReviewRequestDispatchRead(**result), message="Review requests dispatched")


@admin_router.get(
    "/product/{product_id}",
    response_model=ApiResponse[list[ReviewRead]],
    summary="List every review on a product, hidden ones included",
)
async def list_product_reviews_for_moderation(
    product_id: UUID,
    params: Annotated[PageParams, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[ReviewRead]]:
    reviews, total = await ReviewService(session, user.tenant_id).list_for_product(
        product_id, params, approved_only=False
    )
    return paginated(
        [ReviewRead.model_validate(review) for review in reviews],
        total_items=total,
        params=params,
        message="Reviews retrieved",
    )


@admin_router.get(
    "/product/{product_id}/summary",
    response_model=ApiResponse[RatingSummaryRead],
    summary="Rating summary counting hidden reviews too",
)
async def get_product_rating_summary_for_moderation(
    product_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_VIEW, legacy_staff=True)),
) -> ApiResponse[RatingSummaryRead]:
    summary = await ReviewService(session, user.tenant_id).summary(
        product_id, approved_only=False
    )
    return ok(summary, message="Rating summary retrieved")


@admin_router.patch(
    "/{review_id}",
    response_model=ApiResponse[ReviewRead],
    summary="Approve or hide a review",
)
async def moderate_review(
    review_id: UUID,
    data: ReviewModerate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REVIEWS_MANAGE)),
) -> ApiResponse[ReviewRead]:
    review = await ReviewService(session, user.tenant_id).moderate(review_id, data)
    return ok(ReviewRead.model_validate(review), message="Review moderated")
