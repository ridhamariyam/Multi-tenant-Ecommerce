"""AI generation jobs and the credit ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.constants import JOB_STATUSES, LEDGER_ENTRIES
from app.models.base import Base, IdMixin, TenantMixin, TimestampMixin


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


class AiGenerationJob(IdMixin, TenantMixin, TimestampMixin, Base):
    """ONE product image + ONE virtual model = one try-on request (1..4 outputs)."""

    __tablename__ = "ai_generation_jobs"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_ai_generation_jobs_tenant_id_id"),
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_ai_generation_jobs_tenant_idempotency_key"
        ),
        UniqueConstraint(
            "provider", "provider_prediction_id", name="uq_ai_generation_jobs_provider_prediction"
        ),
        CheckConstraint(_in("status", JOB_STATUSES), name="status_valid"),
        CheckConstraint("num_images BETWEEN 1 AND 4", name="num_images_valid"),
        CheckConstraint("credits_reserved >= 0", name="credits_reserved_valid"),
        CheckConstraint("credits_charged IS NULL OR credits_charged >= 0", name="credits_charged_valid"),
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_ai_generation_jobs_tenant_product_products",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "product_image_id"],
            ["product_images.tenant_id", "product_images.id"],
            name="fk_ai_generation_jobs_tenant_product_image_product_images",
            ondelete="SET NULL (product_image_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "created_by_user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_ai_generation_jobs_tenant_created_by_users",
            ondelete="SET NULL (created_by_user_id)",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "parent_job_id"],
            ["ai_generation_jobs.tenant_id", "ai_generation_jobs.id"],
            name="fk_ai_generation_jobs_tenant_parent_ai_generation_jobs",
            ondelete="SET NULL (parent_job_id)",
        ),
        ForeignKeyConstraint(
            ["virtual_model_id"],
            ["virtual_models.id"],
            name="fk_ai_generation_jobs_virtual_model_id_virtual_models",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["pose_id"],
            ["virtual_model_poses.id"],
            name="fk_ai_generation_jobs_pose_id_virtual_model_poses",
            ondelete="SET NULL",
        ),
        Index("ix_ai_generation_jobs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_ai_generation_jobs_tenant_id_product_id", "tenant_id", "product_id"),
        Index(
            "ix_ai_generation_jobs_active",
            "status",
            "updated_at",
            postgresql_where=text("status IN ('queued', 'starting', 'processing')"),
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_image_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    virtual_model_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pose_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    parent_job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    provider_model: Mapped[str] = mapped_column(String(50), nullable=False)
    provider_prediction_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

    resolution: Mapped[str] = mapped_column(String(5), nullable=False)
    generation_mode: Mapped[str] = mapped_column(String(10), nullable=False)
    output_format: Mapped[str] = mapped_column(String(5), nullable=False)
    num_images: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="queued", server_default=text("'queued'")
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    request_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    error_code: Mapped[str | None] = mapped_column(String(60), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    credits_reserved: Mapped[int] = mapped_column(Integer, nullable=False)
    credits_charged: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # What the provider reported billing us (x-fashn-credits-used); not the brand's price.
    provider_credits: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AiUsageLedger(IdMixin, TenantMixin, Base):
    """Append-only credit movements. A brand's balance is the sum of `credits`.

    One RESERVE, one RELEASE and one CHARGE per job at most (unique), so a
    repeated request, task or webhook can never bill twice.
    """

    __tablename__ = "ai_usage_ledger"

    __table_args__ = (
        CheckConstraint(_in("entry_type", LEDGER_ENTRIES), name="entry_type_valid"),
        CheckConstraint(
            "(entry_type IN ('RESERVE', 'CHARGE') AND credits <= 0)"
            " OR (entry_type IN ('GRANT', 'RELEASE') AND credits >= 0)"
            " OR entry_type = 'ADJUST'",
            name="credit_sign_valid",
        ),
        CheckConstraint(
            "(entry_type IN ('RESERVE', 'RELEASE', 'CHARGE')) = (job_id IS NOT NULL)",
            name="job_entries_have_job",
        ),
        UniqueConstraint("tenant_id", "job_id", "entry_type", name="uq_ai_usage_ledger_job_entry"),
        UniqueConstraint("tenant_id", "reference", name="uq_ai_usage_ledger_reference"),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["ai_generation_jobs.tenant_id", "ai_generation_jobs.id"],
            name="fk_ai_usage_ledger_tenant_job_ai_generation_jobs",
            ondelete="CASCADE",
        ),
        Index("ix_ai_usage_ledger_tenant_id_created_at", "tenant_id", "created_at"),
    )

    entry_type: Mapped[str] = mapped_column(String(10), nullable=False)
    credits: Mapped[int] = mapped_column(Integer, nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Makes grants idempotent, e.g. "plan:STARTER:2026-11-01".
    reference: Mapped[str | None] = mapped_column(String(120), nullable=True)
    note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
