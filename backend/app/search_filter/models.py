from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, IdMixin, TenantMixin
from app.search_filter.constants import MAX_QUERY_LENGTH


class SearchHistory(IdMixin, TenantMixin, Base):
    """One row per phrase a shopper has searched; a repeat bumps searched_at."""

    __tablename__ = "search_history"

    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_search_history_tenant_id_id"),
        UniqueConstraint(
            "tenant_id",
            "user_id",
            "query",
            name="uq_search_history_tenant_user_query",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_search_history_tenant_user_users",
            ondelete="CASCADE",
        ),
        Index(
            "ix_search_history_tenant_id_user_id_searched_at",
            "tenant_id",
            "user_id",
            "searched_at",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    query: Mapped[str] = mapped_column(String(MAX_QUERY_LENGTH), nullable=False)

    # Set in Python, not by the server: recency is the ordering key here, and
    # now() would tie every row written inside one transaction.
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
