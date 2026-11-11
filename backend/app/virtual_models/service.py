"""The character library: platform admins curate it, brands choose from it."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.uploads import check_image
from app.core.error_codes import VirtualModelErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.storage import StorageError, get_storage
from app.media.constants import MediaKind, Visibility
from app.media.models import MediaAsset
from app.media.service import store_asset
from app.virtual_models.constants import MAX_POSES_PER_MODEL
from app.virtual_models.models import VirtualModel, VirtualModelPose
from app.virtual_models.schemas import (
    PoseRead,
    VirtualModelAdminRead,
    VirtualModelCreate,
    VirtualModelRead,
    VirtualModelUpdate,
)

NOT_FOUND = "Virtual model not found"
NAME_TAKEN = "A virtual model with that name already exists"


class VirtualModelService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list(self, *, include_inactive: bool) -> list[VirtualModel]:
        query = select(VirtualModel).order_by(VirtualModel.name)
        if not include_inactive:
            query = query.where(VirtualModel.is_active.is_(True))
        return list((await self.session.scalars(query)).all())

    async def get(self, model_id: uuid.UUID, *, include_inactive: bool) -> VirtualModel:
        model = await self.session.get(VirtualModel, model_id)
        # An inactive character looks the same as a missing one to brands.
        if model is None or (not include_inactive and not model.is_active):
            raise NotFoundError(NOT_FOUND, error_code=VirtualModelErrorCode.NOT_FOUND)
        return model

    async def get_active_for_generation(self, model_id: uuid.UUID) -> VirtualModel:
        model = await self.session.get(VirtualModel, model_id)
        if model is None:
            raise NotFoundError(NOT_FOUND, error_code=VirtualModelErrorCode.NOT_FOUND)
        if not model.is_active or model.image_asset_id is None:
            raise ValidationError(
                "That virtual model is not available", error_code=VirtualModelErrorCode.INACTIVE
            )
        return model

    async def create(self, data: VirtualModelCreate) -> VirtualModel:
        model = VirtualModel(**data.model_dump(), is_active=False)
        self.session.add(model)
        await self._commit()
        await self.session.refresh(model)
        return model

    async def update(self, model_id: uuid.UUID, data: VirtualModelUpdate) -> VirtualModel:
        model = await self.get(model_id, include_inactive=True)
        changes = data.model_dump(exclude_unset=True)
        if changes.get("is_active") and model.image_asset_id is None:
            raise ValidationError(
                "Upload a photo before activating this model",
                error_code=VirtualModelErrorCode.NO_IMAGE,
            )
        for field, value in changes.items():
            # Only the free-text fields can be cleared; null elsewhere means "unchanged".
            if value is None and field not in {"description", "license_note"}:
                continue
            setattr(model, field, value)
        await self._commit()
        await self.session.refresh(model)
        return model

    async def add_image(
        self,
        model_id: uuid.UUID,
        *,
        content_type: str,
        data: bytes,
        label: str | None,
        primary: bool,
    ) -> VirtualModel:
        model = await self.get(model_id, include_inactive=True)
        if not primary:
            count = await self.session.scalar(
                select(func.count()).where(VirtualModelPose.virtual_model_id == model.id)
            )
            if (count or 0) >= MAX_POSES_PER_MODEL:
                raise ValidationError(
                    f"A model can have at most {MAX_POSES_PER_MODEL} poses",
                    error_code=VirtualModelErrorCode.TOO_MANY_POSES,
                )
        image = check_image(content_type, data)
        key = f"platform/virtual-models/{model.id}/{uuid.uuid4().hex}{image.extension}"
        asset = await store_asset(
            self.session,
            data=data,
            image=image,
            key=key,
            kind=MediaKind.VIRTUAL_MODEL,
            visibility=Visibility.PUBLIC,
            tenant_id=None,
        )
        if primary or model.image_asset_id is None:
            model.image_asset_id = asset.id
        if not primary:
            self.session.add(
                VirtualModelPose(virtual_model_id=model.id, asset_id=asset.id, label=label)
            )
        await self.session.commit()
        await self.session.refresh(model)
        return model

    async def remove_pose(self, model_id: uuid.UUID, pose_id: uuid.UUID) -> None:
        model = await self.get(model_id, include_inactive=True)
        pose = await self.session.get(VirtualModelPose, pose_id)
        if pose is None or pose.virtual_model_id != model.id:
            raise NotFoundError("Pose not found", error_code=VirtualModelErrorCode.NOT_FOUND)
        asset = await self.session.get(MediaAsset, pose.asset_id)
        await self.session.delete(pose)
        await self.session.flush()  # the pose row references the asset: remove it first
        if asset is not None and model.image_asset_id != asset.id:
            await self.session.delete(asset)
            key = asset.storage_key
        else:
            key = None
        await self.session.commit()
        if key:
            try:
                await get_storage().delete(key)
            except StorageError:
                pass  # the row is gone; an orphaned object is harmless

    async def _commit(self) -> None:
        try:
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            if "uq_virtual_models_name" in str(exc.orig):
                raise ConflictError(NAME_TAKEN, error_code=VirtualModelErrorCode.NAME_TAKEN) from exc
            raise

    async def poses_for(self, model: VirtualModel) -> list[tuple[VirtualModelPose, MediaAsset]]:
        rows = await self.session.execute(
            select(VirtualModelPose, MediaAsset)
            .join(MediaAsset, MediaAsset.id == VirtualModelPose.asset_id)
            .where(VirtualModelPose.virtual_model_id == model.id)
            .order_by(VirtualModelPose.sort_order, VirtualModelPose.created_at)
        )
        return [(pose, asset) for pose, asset in rows.all()]

    async def read(self, model: VirtualModel, *, admin: bool = False):
        image = (
            await self.session.get(MediaAsset, model.image_asset_id)
            if model.image_asset_id
            else None
        )
        poses = [
            PoseRead(
                id=pose.id,
                label=pose.label,
                url=asset.url or "",
                width=asset.width,
                height=asset.height,
                sort_order=pose.sort_order,
            )
            for pose, asset in await self.poses_for(model)
        ]
        fields = dict(
            id=model.id,
            name=model.name,
            description=model.description,
            gender_presentation=model.gender_presentation,
            model_type=model.model_type,
            available_categories=list(model.available_categories or []),
            supported_garments=list(model.supported_garments or []),
            image_url=image.url if image else None,
            poses=poses,
            is_active=model.is_active,
            created_at=model.created_at,
        )
        if admin:
            return VirtualModelAdminRead(
                **fields, license_note=model.license_note, updated_at=model.updated_at
            )
        return VirtualModelRead(**fields)
