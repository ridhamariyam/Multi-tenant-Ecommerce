"""Record and read the admin activity log."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.models import AuditLog
from app.audit.schemas import AuditLogQuery
from app.core.repository import TenantScopedRepository
from app.core.request_context import client_ip
from app.users.models import User

_SECRET_HINTS = ("password", "token", "secret", "otp")


def _scrub(value: Any) -> Any:
    """Drop anything that looks like a credential before it is stored."""
    if isinstance(value, dict):
        return {
            key: "***" if any(hint in str(key).lower() for hint in _SECRET_HINTS) else _scrub(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    return value


class AuditLogRepository(TenantScopedRepository[AuditLog]):
    model = AuditLog


async def record_activity(
    session: AsyncSession,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: object | None = None,
    *,
    summary: str | None = None,
    changes: Any = None,
    request: Request | None = None,
    commit: bool = True,
) -> AuditLog:
    """Append one entry for `actor` in the actor's own tenant."""
    entry = AuditLog(
        tenant_id=actor.tenant_id,
        actor_id=actor.id,
        actor_name=actor.name or actor.email or actor.phone,
        actor_role=actor.role,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=(summary or "")[:255] or None,
        changes=_scrub(jsonable_encoder(changes)) if changes is not None else None,
        ip_address=client_ip(request) if request is not None else None,
    )
    session.add(entry)
    if request is not None:
        # Tells the automatic trail this request is already on record.
        request.state.audit_recorded = True
    if commit:
        await session.commit()
    else:
        await session.flush()
    return entry


async def record_login(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    user: User | None,
    portal: str,
    success: bool,
    request: Request | None = None,
) -> None:
    """A sign-in attempt on the admin or staff login. Never stores what was typed:
    an unknown account is logged without the identifier (it may be a mistyped password).
    The caller commits."""
    if success:
        action, summary = "auth.login", f"Signed in ({portal})"
    else:
        action = "auth.login_failed"
        summary = f"Failed {portal} sign-in" + ("" if user else " (unknown account)")
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=user.id if user else None,
            actor_name=(user.name or user.email or user.phone) if user else None,
            actor_role=user.role if user else None,
            action=action,
            entity_type="session",
            entity_id=str(user.id) if user else None,
            summary=summary,
            ip_address=client_ip(request) if request is not None else None,
        )
    )


class AuditService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.logs = AuditLogRepository(session, tenant_id)

    async def list(self, query: AuditLogQuery) -> tuple[list[AuditLog], int]:
        stmt = self.logs.base_select()
        if query.actor_id is not None:
            stmt = stmt.where(AuditLog.actor_id == query.actor_id)
        if query.entity_type:
            stmt = stmt.where(AuditLog.entity_type == query.entity_type)
        if query.entity_id:
            stmt = stmt.where(AuditLog.entity_id == query.entity_id)
        if query.action:
            stmt = stmt.where(AuditLog.action.startswith(query.action))
        if query.start_date:
            start = datetime.combine(query.start_date, time.min, tzinfo=timezone.utc)
            stmt = stmt.where(AuditLog.created_at >= start)
        if query.end_date:
            day_after = query.end_date + timedelta(days=1)
            end = datetime.combine(day_after, time.min, tzinfo=timezone.utc)
            stmt = stmt.where(AuditLog.created_at < end)
        rows, total = await self.logs.paginate(
            stmt.order_by(AuditLog.created_at.desc(), AuditLog.id), query
        )
        return list(rows), total
