"""Shared virtual character library.

Brands (any member who can view the catalogue) browse active characters.
Platform administrators create, edit, photograph and (de)activate them.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.merchants.dependencies import PlatformAdmin
from app.users.models import User
from app.virtual_models.schemas import (
    VirtualModelAdminRead,
    VirtualModelCreate,
    VirtualModelRead,
    VirtualModelUpdate,
)
from app.virtual_models.service import VirtualModelService

router = APIRouter(prefix="/platform/virtual-models", tags=["Virtual Models"])
admin_router = APIRouter(prefix="/platform/admin/virtual-models", tags=["Platform Admin"])

BrandViewer = Depends(require_permission(Permission.CATALOGUE_VIEW))


@router.get("", response_model=ApiResponse[list[VirtualModelRead]], summary="Active characters")
async def list_models(
    response: Response, user: User = BrandViewer, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[VirtualModelRead]]:
    service = VirtualModelService(session)
    models = await service.list(include_inactive=False)
    return ok([await service.read(m) for m in models], message="Virtual models")


@router.get("/{model_id}", response_model=ApiResponse[VirtualModelRead], summary="One character")
async def get_model(
    model_id: UUID, user: User = BrandViewer, session: AsyncSession = Depends(get_db)
) -> ApiResponse[VirtualModelRead]:
    service = VirtualModelService(session)
    return ok(await service.read(await service.get(model_id, include_inactive=False)))


@router.post(
    "",
    response_model=ApiResponse[VirtualModelAdminRead],
    status_code=status.HTTP_201_CREATED,
    summary="Create a character (platform admin; starts inactive)",
)
async def create_model(
    data: VirtualModelCreate, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[VirtualModelAdminRead]:
    service = VirtualModelService(session)
    model = await service.create(data)
    return ok(await service.read(model, admin=True), message="Virtual model created")


@router.put(
    "/{model_id}",
    response_model=ApiResponse[VirtualModelAdminRead],
    summary="Edit or (de)activate a character (platform admin)",
)
async def update_model(
    model_id: UUID,
    data: VirtualModelUpdate,
    admin: PlatformAdmin,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[VirtualModelAdminRead]:
    service = VirtualModelService(session)
    model = await service.update(model_id, data)
    return ok(await service.read(model, admin=True), message="Virtual model updated")


@admin_router.get(
    "", response_model=ApiResponse[list[VirtualModelAdminRead]], summary="All characters"
)
async def admin_list_models(
    admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[VirtualModelAdminRead]]:
    service = VirtualModelService(session)
    models = await service.list(include_inactive=True)
    return ok([await service.read(m, admin=True) for m in models], message="Virtual models")


@admin_router.get(
    "/{model_id}", response_model=ApiResponse[VirtualModelAdminRead], summary="One character"
)
async def admin_get_model(
    model_id: UUID, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> ApiResponse[VirtualModelAdminRead]:
    service = VirtualModelService(session)
    return ok(await service.read(await service.get(model_id, include_inactive=True), admin=True))


@admin_router.post(
    "/{model_id}/images",
    response_model=ApiResponse[VirtualModelAdminRead],
    status_code=status.HTTP_201_CREATED,
    summary="Upload the main photo (primary=true) or an extra pose",
)
async def upload_model_image(
    model_id: UUID,
    admin: PlatformAdmin,
    file: UploadFile = File(description="JPEG, PNG or WebP"),
    primary: bool = Form(default=False),
    label: str | None = Form(default=None, max_length=100),
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[VirtualModelAdminRead]:
    service = VirtualModelService(session)
    model = await service.add_image(
        model_id,
        content_type=file.content_type or "",
        data=await file.read(get_settings().max_upload_bytes + 1),
        label=label.strip() if label and label.strip() else None,
        primary=primary,
    )
    return ok(await service.read(model, admin=True), message="Image added")


@admin_router.delete(
    "/{model_id}/poses/{pose_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an extra pose",
)
async def delete_pose(
    model_id: UUID, pose_id: UUID, admin: PlatformAdmin, session: AsyncSession = Depends(get_db)
) -> Response:
    await VirtualModelService(session).remove_pose(model_id, pose_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
