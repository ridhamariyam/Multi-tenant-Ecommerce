from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.schemas import AuditLogQuery, AuditLogRead
from app.audit.service import AuditService
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.responses import ApiResponse, paginated
from app.users.models import User

router = APIRouter(prefix="/admin/audit-logs", tags=["Admin-Audit"])


@router.get("", response_model=ApiResponse[list[AuditLogRead]], summary="Activity log")
async def list_audit_logs(
    params: Annotated[AuditLogQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.AUDIT_VIEW)),
) -> ApiResponse[list[AuditLogRead]]:
    logs, total = await AuditService(session, user.tenant_id).list(params)
    return paginated(
        [AuditLogRead.model_validate(log) for log in logs],
        total_items=total,
        params=params,
        message="Activity retrieved",
    )
