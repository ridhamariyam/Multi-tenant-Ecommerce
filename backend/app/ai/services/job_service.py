"""AI try-on jobs: accept, submit to the provider, track, store results.

Request path (API):  create_job -> row + credit reservation, committed -> enqueue submit
Worker path:         submit_job -> provider prediction id -> poll_job (repeats) ->
                     outputs copied into our private bucket -> credits settled

Every step re-reads the job under a row lock and does nothing unless the job is
in the state that step expects, so repeated tasks, duplicate webhooks and
concurrent polls are harmless. One product image + one virtual model per job:
combining several garments into one outfit is not attempted.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.constants import ACTIVE_STATUSES, FINAL_STATUSES, JobStatus, credits_for
from app.ai.models import AiGenerationJob
from app.ai.providers.base import ProviderError, TryOnProvider, TryOnRequest
from app.ai.providers.registry import get_provider
from app.ai.services import usage_service
from app.ai.services.slots import acquire_slot, release_slot
from app.catalogue.models import Product, ProductImage
from app.core.config import get_settings
from app.core.error_codes import AiErrorCode, ProductErrorCode, VirtualModelErrorCode
from app.core.exceptions import (
    AppError,
    ConflictError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
)
from app.core.storage import LocalStorage, StorageError, get_storage, private_key
from app.media.constants import MediaKind, ReviewStatus, Visibility
from app.media.models import MediaAsset
from app.media.service import require_object_storage, store_asset
from app.subscriptions.service import SubscriptionService
from app.virtual_models.models import VirtualModel, VirtualModelPose
from app.virtual_models.service import VirtualModelService

logger = logging.getLogger(__name__)

# Generated images can be large (4k PNG); product photos follow the upload limit.
MAX_OUTPUT_BYTES = 40 * 1024 * 1024
THUMBNAIL_SIZE = 480

NOT_CONFIGURED = (
    "AI generation is not configured. Set AI_PROVIDER=fashn and FASHN_API_KEY in the "
    "backend environment (or AI_PROVIDER=mock for a labelled local preview in development)."
)
JOB_NOT_FOUND = "AI job not found"


class ProviderNotConfiguredError(AppError):
    status_code = 503
    error_code = AiErrorCode.PROVIDER_NOT_CONFIGURED
    default_message = NOT_CONFIGURED


@dataclass(frozen=True)
class GenerationRequest:
    product_id: uuid.UUID
    virtual_model_id: uuid.UUID
    product_image_id: uuid.UUID | None
    pose_id: uuid.UUID | None
    resolution: str
    generation_mode: str
    output_format: str
    num_images: int
    seed: int | None
    prompt: str | None

    def fingerprint(self) -> str:
        payload = json.dumps({k: str(v) for k, v in self.__dict__.items()}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------- images


async def read_stored_image(url: str) -> tuple[bytes, str]:
    """Bytes of an image this platform stored itself. Anything else is refused.

    Product images may point at any https URL; fetching those server-side would
    let a brand aim the worker at internal addresses, so only our own files
    (the bucket, or the legacy /media disk) can be sent for generation.
    """
    settings = get_settings()
    candidates = [get_storage()]
    if settings.storage_backend != "local":
        candidates.append(LocalStorage(Path(settings.storage_local_path), settings.storage_public_base_url))
    for storage in candidates:
        key = storage.key_for_url(url)  # type: ignore[attr-defined]
        if key is None:
            continue
        try:
            stored = await storage.read(key, max_bytes=MAX_OUTPUT_BYTES)  # type: ignore[attr-defined]
        except StorageError as exc:
            raise ProviderError("StorageError", "Could not read the stored image", retryable=True) from exc
        if stored is None:
            break
        return stored.data, check_image_for_ai(stored.data)
    raise ProviderError(
        "ImageNotStored", "The image is not stored on this platform", retryable=False
    )


def check_image_for_ai(data: bytes) -> str:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
            fmt = image.format
    except Exception as exc:
        raise ProviderError("BadImage", "Stored image could not be read", retryable=False) from exc
    return {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}.get(fmt or "", "image/jpeg")


def _thumbnail(data: bytes) -> bytes:
    with Image.open(io.BytesIO(data)) as image:
        image = image.convert("RGB")
        image.thumbnail((THUMBNAIL_SIZE, THUMBNAIL_SIZE))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()


# ------------------------------------------------------------- accepting


class JobService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    async def get(self, job_id: uuid.UUID) -> AiGenerationJob:
        job = await self.session.scalar(
            select(AiGenerationJob).where(
                AiGenerationJob.tenant_id == self.tenant_id, AiGenerationJob.id == job_id
            )
        )
        if job is None:
            raise NotFoundError(JOB_NOT_FOUND, error_code=AiErrorCode.JOB_NOT_FOUND)
        return job

    async def list(self, *, product_id: uuid.UUID | None, status: str | None, limit: int, offset: int):
        query = select(AiGenerationJob).where(AiGenerationJob.tenant_id == self.tenant_id)
        if product_id:
            query = query.where(AiGenerationJob.product_id == product_id)
        if status:
            query = query.where(AiGenerationJob.status == status)
        total = await self.session.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.session.scalars(
            query.order_by(AiGenerationJob.created_at.desc()).limit(limit).offset(offset)
        )
        return list(rows.all()), int(total or 0)

    async def outputs(self, job: AiGenerationJob) -> list[MediaAsset]:
        rows = await self.session.scalars(
            select(MediaAsset)
            .where(
                MediaAsset.tenant_id == self.tenant_id,
                MediaAsset.job_id == job.id,
                MediaAsset.kind == MediaKind.AI_GENERATED.value,
            )
            .order_by(MediaAsset.output_index)
        )
        return list(rows.all())

    async def _product_image(self, product: Product, image_id: uuid.UUID | None) -> ProductImage:
        query = select(ProductImage).where(
            ProductImage.tenant_id == self.tenant_id,
            ProductImage.product_id == product.id,
            ProductImage.source == "UPLOAD",
        )
        if image_id is not None:
            image = await self.session.scalar(query.where(ProductImage.id == image_id))
        else:
            image = await self.session.scalar(
                query.order_by(ProductImage.is_primary.desc(), ProductImage.sort_order, ProductImage.created_at)
            )
        if image is None:
            raise ValidationError(
                "Upload a product photo first (AI generation uses the brand's own product image)",
                error_code=AiErrorCode.PRODUCT_HAS_NO_IMAGE,
            )
        storage = get_storage()
        settings = get_settings()
        ours = storage.key_for_url(image.url) is not None or image.url.startswith(  # type: ignore[attr-defined]
            settings.storage_public_base_url.rstrip("/") + "/"
        )
        if not ours:
            raise ValidationError(
                "That product image is an external link. Upload the photo to this store to use it "
                "for AI generation.",
                error_code=AiErrorCode.PRODUCT_HAS_NO_IMAGE,
            )
        return image

    async def create(
        self,
        data: GenerationRequest,
        *,
        user_id: uuid.UUID | None,
        idempotency_key: str | None,
        parent_job_id: uuid.UUID | None = None,
    ) -> tuple[AiGenerationJob, bool]:
        """Validate, reserve credits and queue. Returns (job, created)."""
        provider = get_provider()
        if provider is None:
            raise ProviderNotConfiguredError()
        require_object_storage()
        fingerprint = data.fingerprint()

        if idempotency_key:
            existing = await self._by_idempotency_key(idempotency_key)
            if existing is not None:
                return self._replay(existing, fingerprint), False

        await SubscriptionService(self.session, self.tenant_id).require_feature("ai_studio")

        product = await self.session.scalar(
            select(Product).where(Product.tenant_id == self.tenant_id, Product.id == data.product_id)
        )
        if product is None:
            raise NotFoundError("Product not found", error_code=ProductErrorCode.PRODUCT_NOT_FOUND)
        image = await self._product_image(product, data.product_image_id)

        model = await VirtualModelService(self.session).get_active_for_generation(data.virtual_model_id)
        if data.pose_id is not None:
            pose = await self.session.get(VirtualModelPose, data.pose_id)
            if pose is None or pose.virtual_model_id != model.id:
                raise NotFoundError("Pose not found", error_code=VirtualModelErrorCode.NOT_FOUND)

        settings = get_settings()
        active = await self.session.scalar(
            select(func.count()).where(
                AiGenerationJob.tenant_id == self.tenant_id,
                AiGenerationJob.status.in_(ACTIVE_STATUSES),
            )
        )
        if (active or 0) >= settings.ai_max_active_jobs_per_brand:
            raise ConflictError(
                "Too many generations in progress. Wait for some to finish.",
                error_code=AiErrorCode.TOO_MANY_ACTIVE_JOBS,
            )

        credits = credits_for(data.generation_mode, data.resolution, data.num_images)
        job = AiGenerationJob(
            id=uuid.uuid4(),
            tenant_id=self.tenant_id,
            product_id=product.id,
            product_image_id=image.id,
            virtual_model_id=model.id,
            pose_id=data.pose_id,
            created_by_user_id=user_id,
            parent_job_id=parent_job_id,
            provider=provider.name,
            provider_model=provider.model_name,
            resolution=data.resolution,
            generation_mode=data.generation_mode,
            output_format=data.output_format,
            num_images=data.num_images,
            seed=data.seed,
            prompt=data.prompt,
            status=JobStatus.QUEUED.value,
            idempotency_key=idempotency_key,
            request_hash=fingerprint,
            credits_reserved=credits,
            timeout_at=_now() + timedelta(seconds=settings.ai_job_timeout_seconds),
        )
        try:
            await usage_service.lock_brand_credits(self.session, self.tenant_id)
            self.session.add(job)
            await self.session.flush()
            await usage_service.reserve(self.session, self.tenant_id, job.id, credits)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            if idempotency_key:  # the same key raced us: answer with the winner
                existing = await self._by_idempotency_key(idempotency_key)
                if existing is not None:
                    return self._replay(existing, fingerprint), False
            raise
        except Exception:
            await self.session.rollback()
            raise
        await self.session.refresh(job)
        return job, True

    async def _by_idempotency_key(self, key: str) -> AiGenerationJob | None:
        return await self.session.scalar(
            select(AiGenerationJob).where(
                AiGenerationJob.tenant_id == self.tenant_id, AiGenerationJob.idempotency_key == key
            )
        )

    @staticmethod
    def _replay(job: AiGenerationJob, fingerprint: str) -> AiGenerationJob:
        if job.request_hash != fingerprint:
            raise ConflictError(
                "This Idempotency-Key was already used for a different generation request",
                error_code=AiErrorCode.IDEMPOTENCY_CONFLICT,
            )
        return job

    async def cancel(self, job_id: uuid.UUID) -> AiGenerationJob:
        job = await self._locked(job_id)
        if job.status != JobStatus.QUEUED.value:
            await self.session.rollback()
            raise ConflictError(
                "Only queued generations can be cancelled; the provider has no cancel operation "
                "once a job is submitted.",
                error_code=AiErrorCode.NOT_CANCELLABLE,
            )
        await _finish(self.session, job, JobStatus.CANCELLED, charge=0, error=("Cancelled", "Cancelled by the brand"))
        await self.session.commit()
        await release_slot(job.provider, job.id)
        return job

    async def retry(
        self, job_id: uuid.UUID, *, user_id: uuid.UUID | None, idempotency_key: str | None, seed: int | None
    ) -> tuple[AiGenerationJob, bool]:
        """A new job with the same inputs (retry a failure, or regenerate a result)."""
        job = await self.get(job_id)
        if job.status not in FINAL_STATUSES:
            raise ConflictError(
                "This generation is still running", error_code=AiErrorCode.NOT_RETRYABLE
            )
        request = GenerationRequest(
            product_id=job.product_id,
            virtual_model_id=job.virtual_model_id,
            product_image_id=job.product_image_id,
            pose_id=job.pose_id,
            resolution=job.resolution,
            generation_mode=job.generation_mode,
            output_format=job.output_format,
            num_images=job.num_images,
            seed=seed if seed is not None else (None if job.seed is None else (job.seed + 1) % (2**31)),
            prompt=job.prompt,
        )
        return await self.create(
            request, user_id=user_id, idempotency_key=idempotency_key, parent_job_id=job.id
        )

    async def _locked(self, job_id: uuid.UUID) -> AiGenerationJob:
        job = await self.session.scalar(
            select(AiGenerationJob)
            .where(AiGenerationJob.tenant_id == self.tenant_id, AiGenerationJob.id == job_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None:
            raise NotFoundError(JOB_NOT_FOUND, error_code=AiErrorCode.JOB_NOT_FOUND)
        return job


# ------------------------------------------------------------- finishing


async def _finish(
    session: AsyncSession,
    job: AiGenerationJob,
    status: JobStatus,
    *,
    charge: int,
    error: tuple[str, str] | None = None,
) -> None:
    """Move a job to a final state and settle its credits, once."""
    if job.status in FINAL_STATUSES:
        return
    job.status = status.value
    job.finished_at = _now()
    if error:
        job.error_code, job.error_message = error[0][:60], error[1][:2000]
    job.credits_charged = charge
    await usage_service.lock_brand_credits(session, job.tenant_id)
    await usage_service.settle(session, job.tenant_id, job.id, reserved=job.credits_reserved, charge=charge)


async def _lock_job(session: AsyncSession, job_id: uuid.UUID) -> AiGenerationJob | None:
    """The job under a row lock, or None if missing or another worker holds it."""
    try:
        return await session.scalar(
            select(AiGenerationJob)
            .where(AiGenerationJob.id == job_id)
            .with_for_update(nowait=True)
            .execution_options(populate_existing=True)
        )
    except OperationalError:  # lock held: someone else is handling this job right now
        await session.rollback()
        return None


@dataclass(frozen=True)
class StepResult:
    """What the worker should do next with this job."""

    poll_in: float | None = None  # seconds until the next status check
    submit_in: float | None = None  # seconds until submission is retried


async def submit_job(session: AsyncSession, job_id: uuid.UUID, provider: TryOnProvider | None = None) -> StepResult:
    settings = get_settings()
    job = await _lock_job(session, job_id)
    if job is None or job.status != JobStatus.QUEUED.value:
        await session.rollback()
        return StepResult()
    provider = provider or get_provider()
    if provider is None or provider.name != job.provider:
        await _finish(session, job, JobStatus.FAILED, charge=0, error=("ProviderNotConfigured", NOT_CONFIGURED))
        await session.commit()
        return StepResult()
    if _now() >= job.timeout_at:
        await _finish(session, job, JobStatus.FAILED, charge=0, error=("Timeout", "The generation timed out before it could start"))
        await session.commit()
        return StepResult()
    if not await acquire_slot(job.provider, job.id, settings.ai_provider_concurrency, job.timeout_at):
        await session.rollback()
        return StepResult(submit_in=5)

    # Gather inputs while holding the row, then mark it starting and let go of
    # the lock before calling the provider (an HTTP call must not hold a row).
    try:
        request = await _build_request(session, job)
    except ProviderError as exc:
        await _finish(session, job, JobStatus.FAILED, charge=0, error=(exc.code, exc.message))
        await session.commit()
        await release_slot(job.provider, job.id)
        return StepResult()
    job.status = JobStatus.STARTING.value
    job.attempts += 1
    job.submitted_at = _now()
    await session.commit()

    try:
        prediction_id = await provider.generate_tryon(request)
    except ProviderError as exc:
        job = await _lock_job(session, job_id)
        if job is None:
            return StepResult()
        if exc.retryable and job.attempts < settings.ai_max_submit_attempts and _now() < job.timeout_at:
            job.status = JobStatus.QUEUED.value
            job.error_code, job.error_message = exc.code[:60], exc.message[:2000]
            await session.commit()
            await release_slot(job.provider, job.id)
            return StepResult(submit_in=min(60, 5 * 2**job.attempts))
        await _finish(session, job, JobStatus.FAILED, charge=0, error=(exc.code, exc.message))
        await session.commit()
        await release_slot(job.provider, job.id)
        return StepResult()

    job = await _lock_job(session, job_id)
    if job is None:
        # Very unlikely (nobody else touches a starting job without an id);
        # the sweeper will requeue it and the slot expires with the job.
        logger.warning("ai job %s: could not store prediction id", job_id)
        return StepResult()
    job.provider_prediction_id = prediction_id
    job.error_code = job.error_message = None
    await session.commit()
    return StepResult(poll_in=settings.ai_poll_interval_seconds)


async def _build_request(session: AsyncSession, job: AiGenerationJob) -> TryOnRequest:
    image = await session.scalar(
        select(ProductImage).where(
            ProductImage.tenant_id == job.tenant_id, ProductImage.id == job.product_image_id
        )
    )
    if image is None:
        raise ProviderError("ProductImageMissing", "The product image was deleted", retryable=False)
    product_bytes, product_type = await read_stored_image(image.url)

    model = await session.get(VirtualModel, job.virtual_model_id)
    asset_id = model.image_asset_id if model else None
    if job.pose_id is not None:
        pose = await session.get(VirtualModelPose, job.pose_id)
        asset_id = pose.asset_id if pose else asset_id
    asset = await session.get(MediaAsset, asset_id) if asset_id else None
    if model is None or not model.is_active or asset is None or not asset.url:
        raise ProviderError("VirtualModelUnavailable", "The virtual model is no longer available", retryable=False)
    model_bytes, model_type = await read_stored_image(asset.url)

    settings = get_settings()
    webhook = None
    if job.provider == "fashn" and settings.fashn_webhook_secret and settings.public_api_url:
        webhook = (
            f"{settings.public_api_url.rstrip('/')}/api/v1/webhooks/fashn"
            f"?token={settings.fashn_webhook_secret}"
        )
    return TryOnRequest(
        model_image=model_bytes,
        model_image_type=model_type,
        product_image=product_bytes,
        product_image_type=product_type,
        resolution=job.resolution,
        generation_mode=job.generation_mode,
        output_format=job.output_format,
        num_images=job.num_images,
        seed=job.seed,
        prompt=job.prompt,
        webhook_url=webhook,
    )


async def poll_job(session: AsyncSession, job_id: uuid.UUID, provider: TryOnProvider | None = None) -> StepResult:
    settings = get_settings()
    job = await _lock_job(session, job_id)
    if job is None:
        return StepResult()
    if job.status in FINAL_STATUSES or not job.provider_prediction_id:
        await session.rollback()
        return StepResult()
    if _now() >= job.timeout_at:
        await _finish(session, job, JobStatus.FAILED, charge=0, error=("Timeout", "The AI provider did not finish in time"))
        await session.commit()
        await release_slot(job.provider, job.id)
        return StepResult()
    provider = provider or get_provider()
    if provider is None or provider.name != job.provider:
        await session.rollback()
        return StepResult(poll_in=30)  # configuration may come back; the timeout still applies

    try:
        status = await provider.get_status(job.provider_prediction_id)
    except ProviderError as exc:
        job.last_polled_at = _now()
        job.error_code, job.error_message = exc.code[:60], exc.message[:2000]
        await session.commit()
        return StepResult(poll_in=settings.ai_poll_interval_seconds * 3)

    job.last_polled_at = _now()
    if status.state in {"starting", "processing"}:
        job.status = JobStatus.PROCESSING.value if status.state == "processing" else JobStatus.STARTING.value
        await session.commit()
        return StepResult(poll_in=settings.ai_poll_interval_seconds)

    if status.state == "failed":
        job.provider_payload = status.raw
        await _finish(session, job, JobStatus.FAILED, charge=0, error=(status.error_code or "ProviderFailed", status.error_message or "Generation failed"))
        await session.commit()
        await release_slot(job.provider, job.id)
        return StepResult()

    # completed: copy every output into our own bucket before calling it done.
    try:
        stored = await _store_outputs(session, job, provider, status.outputs)
    except ProviderError as exc:
        if exc.retryable:
            await session.commit()  # keep last_polled_at; try again shortly
            return StepResult(poll_in=settings.ai_poll_interval_seconds * 2)
        await _finish(session, job, JobStatus.FAILED, charge=0, error=(exc.code, exc.message))
        await session.commit()
        await release_slot(job.provider, job.id)
        return StepResult()
    except (StorageError, ServiceUnavailableError):
        await session.rollback()
        return StepResult(poll_in=settings.ai_poll_interval_seconds * 3)

    job.provider_payload = status.raw
    job.provider_credits = status.credits_used
    if stored == 0:
        await _finish(session, job, JobStatus.FAILED, charge=0, error=("NoOutput", "The AI provider returned no usable image"))
    else:
        per_image = job.credits_reserved // job.num_images
        await _finish(session, job, JobStatus.COMPLETED, charge=per_image * stored)
    await session.commit()
    await release_slot(job.provider, job.id)
    return StepResult()


async def _store_outputs(session: AsyncSession, job: AiGenerationJob, provider: TryOnProvider, outputs: list[str]) -> int:
    existing = {
        index
        for index in (
            await session.scalars(
                select(MediaAsset.output_index).where(
                    MediaAsset.tenant_id == job.tenant_id,
                    MediaAsset.job_id == job.id,
                    MediaAsset.kind == MediaKind.AI_GENERATED.value,
                )
            )
        ).all()
    }
    stored = len(existing)
    for index, output in enumerate(outputs[: job.num_images]):
        if index in existing:
            continue
        fetched = await provider.handle_result(output, max_bytes=MAX_OUTPUT_BYTES)
        image = _check_large(fetched.data)
        asset = await store_asset(
            session,
            data=fetched.data,
            image=image,
            key=private_key(job.tenant_id, "ai", str(job.id), f"{index}{image.extension}"),
            kind=MediaKind.AI_GENERATED,
            visibility=Visibility.PRIVATE,
            tenant_id=job.tenant_id,
            product_id=job.product_id,
            job_id=job.id,
            review_status=ReviewStatus.PENDING.value,
        )
        asset.output_index = index
        thumb = _thumbnail(fetched.data)
        await store_asset(
            session,
            data=thumb,
            image=_check_large(thumb),
            key=private_key(job.tenant_id, "ai", str(job.id), f"{index}-thumb.jpg"),
            kind=MediaKind.THUMBNAIL,
            visibility=Visibility.PRIVATE,
            tenant_id=job.tenant_id,
            product_id=job.product_id,
            source_asset_id=asset.id,
        )
        stored += 1
    return stored


def _check_large(data: bytes):
    """check_image without the upload size limit (outputs are ours, not uploads)."""
    from app.catalogue.uploads import FORMAT_CONTENT_TYPES, FORMAT_EXTENSIONS, CheckedImage, _validate_image

    try:
        fmt = _validate_image(data)
    except ValidationError as exc:
        raise ProviderError("BadOutput", "The AI provider returned an unreadable image", retryable=False) from exc
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
    return CheckedImage(
        format=fmt, extension=FORMAT_EXTENSIONS[fmt], content_type=FORMAT_CONTENT_TYPES[fmt], width=width, height=height
    )


async def stale_jobs(session: AsyncSession) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """(jobs to submit again, jobs to poll again) for the periodic sweep."""
    settings = get_settings()
    now = _now()
    resubmit = list(
        (
            await session.scalars(
                select(AiGenerationJob.id).where(
                    AiGenerationJob.status == JobStatus.QUEUED.value,
                    AiGenerationJob.updated_at < now - timedelta(seconds=30),
                )
            )
        ).all()
    )
    # Submitted but no prediction id recorded for two minutes: the worker died
    # mid-submit. Put it back in the queue (or fail it once attempts run out).
    orphans = (
        await session.scalars(
            select(AiGenerationJob)
            .where(
                AiGenerationJob.status == JobStatus.STARTING.value,
                AiGenerationJob.provider_prediction_id.is_(None),
                AiGenerationJob.updated_at < now - timedelta(minutes=2),
            )
            .with_for_update(skip_locked=True)
        )
    ).all()
    for job in orphans:
        if job.attempts < settings.ai_max_submit_attempts and now < job.timeout_at:
            job.status = JobStatus.QUEUED.value
            resubmit.append(job.id)
        else:
            await _finish(session, job, JobStatus.FAILED, charge=0, error=("SubmitLost", "Submission to the AI provider was interrupted"))
    await session.commit()
    repoll = list(
        (
            await session.scalars(
                select(AiGenerationJob.id).where(
                    AiGenerationJob.status.in_([JobStatus.STARTING.value, JobStatus.PROCESSING.value]),
                    AiGenerationJob.provider_prediction_id.is_not(None),
                    func.coalesce(AiGenerationJob.last_polled_at, AiGenerationJob.updated_at)
                    < now - timedelta(seconds=settings.ai_poll_interval_seconds * 5),
                )
            )
        ).all()
    )
    return resubmit, repoll


async def job_for_prediction(session: AsyncSession, provider: str, prediction_id: str) -> uuid.UUID | None:
    return await session.scalar(
        select(AiGenerationJob.id).where(
            AiGenerationJob.provider == provider, AiGenerationJob.provider_prediction_id == prediction_id
        )
    )
