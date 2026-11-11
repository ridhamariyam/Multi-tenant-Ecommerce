"""Admin list of return reasons. Orders keep the label they were returned with,
so renaming or switching off a reason never rewrites past orders."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.returns.schemas import ReturnReasonCreate, ReturnReasonRead, ReturnReasonUpdate
from app.returns.service import ReturnReasonService
from app.users.models import User

router = APIRouter(prefix="/admin/return-reasons", tags=["Admin-Returns"], dependencies=AUDITED)

DB = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=ApiResponse[list[ReturnReasonRead]], summary="Return reasons")
async def list_return_reasons(
    session: DB,
    active_only: bool = False,
    user: User = Depends(require_permission(Permission.ORDERS_VIEW, legacy_staff=True)),
):
    rows = await ReturnReasonService(session, user.tenant_id).list(active_only=active_only)
    return ok([ReturnReasonRead.model_validate(r) for r in rows], message="Return reasons")


@router.post(
    "",
    response_model=ApiResponse[ReturnReasonRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a return reason",
)
async def create_return_reason(
    data: ReturnReasonCreate,
    session: DB,
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    reason = await ReturnReasonService(session, user.tenant_id).create(data.label, data.is_active)
    return ok(ReturnReasonRead.model_validate(reason), message="Return reason added")


@router.patch(
    "/{reason_id}",
    response_model=ApiResponse[ReturnReasonRead],
    summary="Rename, reorder or switch a return reason on/off",
)
async def update_return_reason(
    reason_id: UUID,
    data: ReturnReasonUpdate,
    session: DB,
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
):
    reason = await ReturnReasonService(session, user.tenant_id).update(
        reason_id, data.model_dump(exclude_unset=True)
    )
    return ok(ReturnReasonRead.model_validate(reason), message="Return reason updated")
