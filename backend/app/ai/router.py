"""AI studio for brands: put products on virtual models, see credits, approve results.

Generation is asynchronous: creating a job reserves credits and queues it for
the Celery worker; the console polls the job until it completes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.constants import CREDITS_PER_IMAGE, MAX_IMAGES_PER_JOB
from app.ai.models import AiGenerationJob, AiUsageLedger
from app.ai.providers.registry import get_provider
from app.ai.services import job_service, usage_service
from app.ai.services.job_service import GenerationRequest, JobService
from app.ai.workers import dispatch
from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.catalogue.models import ProductImage
from app.core.config import get_settings
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, NotFoundError
from app.core.responses import ApiResponse, ok
from app.core.storage import upload_key
from app.media.constants import MediaKind, ReviewStatus, Visibility
from app.media.models import MediaAsset
from app.media.service import asset_url, require_object_storage, store_asset
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/ai", tags=["Admin-AI"], dependencies=AUDITED)
webhook_router = APIRouter(tags=["AI webhooks"])

CanView = Depends(require_permission(Permission.CATALOGUE_VIEW, legacy_staff=True))
CanGenerate = Depends(require_permission(Permission.CATALOGUE_MANAGE, legacy_staff=True))


class JobCreate(BaseModel):
    product_id: UUID
    virtual_model_id: UUID
    product_image_id: UUID | None = None
    pose_id: UUID | None = None
    resolution: Literal["1k", "2k", "4k"] = "1k"
    generation_mode: Literal["fast", "balanced", "quality"] = "balanced"
    output_format: Literal["png", "jpeg"] = "jpeg"
    num_images: int = Field(default=1, ge=1, le=MAX_IMAGES_PER_JOB)
    seed: int | None = Field(default=None, ge=0, lt=2**31)
    prompt: str | None = Field(default=None, max_length=500)


class OutputRead(BaseModel):
    id: UUID
    url: str | None
    review_status: str | None
    width: int | None
    height: int | None


class JobRead(BaseModel):
    id: UUID
    product_id: UUID
    virtual_model_id: UUID
    status: str
    resolution: str
    generation_mode: str
    num_images: int
    credits_reserved: int
    credits_charged: int | None
    error_message: str | None
    created_at: datetime
    finished_at: datetime | None
    provider: str
    outputs: list[OutputRead] = []


class CreditsRead(BaseModel):
    balance: int
    configured: bool  # an AI provider is set up on the server
    provider: str | None
    price_table: dict[str, int]  # "mode:resolution" -> credits per image
    ledger: list[dict]


async def _output(asset: MediaAsset) -> OutputRead:
    """AI results are private; the console gets a short-lived signed URL."""
    read = OutputRead.model_validate(asset, from_attributes=True)
    try:
        read.url = await asset_url(asset)
    except Exception:  # storage down: show the row without its picture
        read.url = None
    return read


async def _read(service: JobService, job: AiGenerationJob, with_outputs: bool = True) -> JobRead:
    read = JobRead.model_validate(job, from_attributes=True)
    if with_outputs:
        read.outputs = [await _output(a) for a in await service.outputs(job)]
    return read


@router.get("/credits", response_model=ApiResponse[CreditsRead], summary="AI credit balance and recent movements")
async def credits(tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    rows = (
        await session.scalars(
            select(AiUsageLedger).where(AiUsageLedger.tenant_id == user.tenant_id).order_by(AiUsageLedger.created_at.desc()).limit(30)
        )
    ).all()
    provider = get_provider()
    return ok(
        CreditsRead(
            balance=await usage_service.balance(session, user.tenant_id),
            configured=provider is not None,
            provider=provider.name if provider else None,
            price_table={f"{m}:{r}": c for (m, r), c in CREDITS_PER_IMAGE.items()},
            ledger=[
                {"type": r.entry_type, "credits": r.credits, "note": r.note, "at": r.created_at.isoformat()} for r in rows
            ],
        ),
        message="Credits",
    )


@router.post("/jobs", response_model=ApiResponse[JobRead], status_code=201, summary="Generate product photos on a virtual model")
async def create_job(
    data: JobCreate,
    tenant: CurrentTenant,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: AsyncSession = Depends(get_db),
    user: User = CanGenerate,
):
    service = JobService(session, user.tenant_id)
    job, created = await service.create(GenerationRequest(**data.model_dump()), user_id=user.id, idempotency_key=idempotency_key)
    if created:
        dispatch.enqueue_submit(job.id)
    return ok(await _read(service, job), message="Generation queued" if created else "Generation already queued")


@router.get("/jobs", response_model=ApiResponse[list[JobRead]], summary="Recent generations")
async def list_jobs(
    tenant: CurrentTenant,
    product_id: UUID | None = None,
    status: str | None = Query(default=None, max_length=20),
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: AsyncSession = Depends(get_db),
    user: User = CanView,
):
    service = JobService(session, user.tenant_id)
    jobs, _ = await service.list(product_id=product_id, status=status, limit=limit, offset=offset)
    return ok([await _read(service, j) for j in jobs], message="Generations")


@router.get("/jobs/{job_id}", response_model=ApiResponse[JobRead], summary="One generation and its images")
async def get_job(job_id: UUID, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanView):
    service = JobService(session, user.tenant_id)
    return ok(await _read(service, await service.get(job_id)), message="Generation")


@router.post("/jobs/{job_id}/cancel", response_model=ApiResponse[JobRead], summary="Cancel a queued generation")
async def cancel_job(job_id: UUID, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanGenerate):
    service = JobService(session, user.tenant_id)
    return ok(await _read(service, await service.cancel(job_id)), message="Cancelled; credits returned")


@router.post("/jobs/{job_id}/retry", response_model=ApiResponse[JobRead], status_code=201, summary="Generate again with the same inputs")
async def retry_job(
    job_id: UUID,
    tenant: CurrentTenant,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
    session: AsyncSession = Depends(get_db),
    user: User = CanGenerate,
):
    service = JobService(session, user.tenant_id)
    job, created = await service.retry(job_id, user_id=user.id, idempotency_key=idempotency_key, seed=None)
    if created:
        dispatch.enqueue_submit(job.id)
    return ok(await _read(service, job), message="Generation queued")


class Review(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    add_to_product: bool = True


@router.post("/outputs/{asset_id}/review", response_model=ApiResponse[OutputRead], summary="Approve (and use) or reject an AI image")
async def review_output(
    asset_id: UUID, data: Review, tenant: CurrentTenant, session: AsyncSession = Depends(get_db), user: User = CanGenerate
):
    asset = await session.scalar(
        select(MediaAsset).where(MediaAsset.tenant_id == user.tenant_id, MediaAsset.id == asset_id, MediaAsset.job_id.is_not(None))
    )
    if asset is None:
        raise NotFoundError("Image not found")
    asset.review_status = (ReviewStatus.APPROVED if data.decision == "APPROVED" else ReviewStatus.REJECTED).value
    if data.decision == "APPROVED" and data.add_to_product and asset.product_id:
        await _publish_to_product(session, asset)
    await session.commit()
    return ok(await _output(asset), message="Saved")


async def _publish_to_product(session: AsyncSession, asset: MediaAsset) -> None:
    """Copy the private result to a public storefront image and add it to the product (once)."""
    already = await session.scalar(
        select(MediaAsset.id).where(
            MediaAsset.tenant_id == asset.tenant_id,
            MediaAsset.source_asset_id == asset.id,
            MediaAsset.kind == MediaKind.STOREFRONT.value,
        )
    )
    if already is not None:
        return
    stored = await require_object_storage().read(asset.storage_key, max_bytes=40 * 1024 * 1024)
    if stored is None:
        raise NotFoundError("The generated image is no longer in storage")
    image = job_service._check_large(stored.data)
    public = await store_asset(
        session, data=stored.data, image=image, key=upload_key(asset.tenant_id, image.extension),
        kind=MediaKind.STOREFRONT, visibility=Visibility.PUBLIC, tenant_id=asset.tenant_id,
        product_id=asset.product_id, source_asset_id=asset.id,
    )  # fmt: skip
    last = await session.scalar(
        select(func.max(ProductImage.sort_order)).where(
            ProductImage.tenant_id == asset.tenant_id, ProductImage.product_id == asset.product_id
        )
    )
    session.add(
        ProductImage(
            tenant_id=asset.tenant_id, product_id=asset.product_id, url=public.url, alt_text="Model wearing the product",
            sort_order=(last or 0) + 1, is_primary=False, source="AI_GENERATED", media_asset_id=public.id,
        )  # fmt: skip
    )


@webhook_router.post("/webhooks/fashn", response_model=ApiResponse[dict[str, str]], summary="FASHN says a prediction finished")
async def fashn_webhook(request: Request, token: str = Query(max_length=200), session: AsyncSession = Depends(get_db)):
    """The payload is never trusted: it only triggers a status check with FASHN."""
    import hmac

    expected = get_settings().fashn_webhook_secret
    if not expected or not hmac.compare_digest(expected, token):
        raise AuthenticationError("Invalid webhook")
    try:
        body = await request.json()
    except ValueError:
        body = {}
    prediction_id = str(body.get("id") or "") if isinstance(body, dict) else ""
    job_id = await job_service.job_for_prediction(session, "fashn", prediction_id) if prediction_id else None
    if job_id is not None:
        dispatch.enqueue_poll(job_id)
    return ok({"result": "queued" if job_id else "ignored"}, message="Webhook received")
