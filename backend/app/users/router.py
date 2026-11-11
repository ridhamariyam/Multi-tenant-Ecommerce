from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.auth.permissions import PERMISSION_DESCRIPTIONS
from app.core.database import get_db
from app.core.responses import ApiResponse, ok, paginated
from app.users.models import User
from app.users.schemas import (
    PermissionRead,
    StaffCreate,
    StaffPasswordReset,
    StaffQuery,
    StaffRead,
    StaffUpdate,
)
from app.users.serializers import staff_read
from app.users.service import StaffService

admin_router = APIRouter(prefix="/admin/staff", tags=["Admin-Staff"])


@admin_router.get(
    "/permissions",
    response_model=ApiResponse[list[PermissionRead]],
    summary="Every permission that can be granted",
)
async def list_permissions(
    user: User = Depends(require_admin),
) -> ApiResponse[list[PermissionRead]]:
    return ok(
        [PermissionRead(key=p.value, description=d) for p, d in PERMISSION_DESCRIPTIONS.items()],
        message="Permissions retrieved",
    )


@admin_router.get("", response_model=ApiResponse[list[StaffRead]], summary="List staff accounts")
async def list_staff(
    params: Annotated[StaffQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApiResponse[list[StaffRead]]:
    members, total = await StaffService(session, user).list(params)
    return paginated(
        [staff_read(member) for member in members],
        total_items=total,
        params=params,
        message="Staff retrieved",
    )


@admin_router.post(
    "",
    response_model=ApiResponse[StaffRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create an individual staff or admin login",
)
async def create_staff_account(
    data: StaffCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApiResponse[StaffRead]:
    member = await StaffService(session, user).create(data, request)
    return ok(staff_read(member), message="Staff account created")


@admin_router.get(
    "/{staff_id}", response_model=ApiResponse[StaffRead], summary="One staff account"
)
async def get_staff(
    staff_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApiResponse[StaffRead]:
    return ok(staff_read(await StaffService(session, user).get(staff_id)), message="Staff")


@admin_router.patch(
    "/{staff_id}",
    response_model=ApiResponse[StaffRead],
    summary="Change a staff member's name, role, permissions or status",
)
async def update_staff(
    staff_id: UUID,
    data: StaffUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApiResponse[StaffRead]:
    member = await StaffService(session, user).update(staff_id, data, request)
    return ok(staff_read(member), message="Staff account updated")


@admin_router.post(
    "/{staff_id}/password",
    response_model=ApiResponse[StaffRead],
    summary="Set a new password and sign the account out everywhere",
)
async def reset_staff_password(
    staff_id: UUID,
    data: StaffPasswordReset,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> ApiResponse[StaffRead]:
    member = await StaffService(session, user).reset_password(staff_id, data, request)
    return ok(staff_read(member), message="Password updated")
