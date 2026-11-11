"""Who did what in the admin panel, and when."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin


class AuditLog(IdMixin, TenantMixin, Base):
    """One recorded admin action. Append-only."""

    __tablename__ = "audit_logs"

    __table_args__ = (
        # The actor's account may later be erased; the record stays, unnamed.
        ForeignKeyConstraint(
            ["tenant_id", "actor_id"],
            ["users.tenant_id", "users.id"],
            name="fk_audit_logs_tenant_actor_users",
            ondelete="SET NULL (actor_id)",
        ),
        Index("ix_audit_logs_tenant_id_created_at", "tenant_id", "created_at"),
        Index("ix_audit_logs_tenant_id_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_audit_logs_tenant_id_actor_id", "tenant_id", "actor_id"),
    )

    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Snapshots, so the log still reads well if the account changes later.
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(20), nullable=True)

    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # What was sent / what changed (secrets stripped).
    changes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
