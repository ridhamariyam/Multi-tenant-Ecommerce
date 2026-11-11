from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.schemas import AddressCreate, AddressRead, AddressUpdate
from app.addresses.service import AddressService
from app.auth.dependencies import require_customer
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.users.models import User

router = APIRouter(prefix="/addresses", tags=["Addresses"])


def _service(session: AsyncSession, user: User) -> AddressService:
    return AddressService(session, user.tenant_id, user.id)


@router.post(
    "",
    response_model=ApiResponse[AddressRead],
    status_code=status.HTTP_201_CREATED,
    summary="Save a delivery address",
)
async def create_address(
    data: AddressCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[AddressRead]:
    address = await _service(session, user).create(data)
    return ok(AddressRead.model_validate(address), message="Address saved")


@router.get(
    "",
    response_model=ApiResponse[list[AddressRead]],
    summary="List your delivery addresses",
)
async def list_addresses(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[list[AddressRead]]:
    addresses = await _service(session, user).list()
    return ok(
        [AddressRead.model_validate(a) for a in addresses],
        message="Addresses retrieved",
    )


@router.get(
    "/{address_id}",
    response_model=ApiResponse[AddressRead],
    summary="Retrieve a delivery address",
)
async def get_address(
    address_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[AddressRead]:
    address = await _service(session, user).get(address_id)
    return ok(AddressRead.model_validate(address), message="Address retrieved")


@router.patch(
    "/{address_id}",
    response_model=ApiResponse[AddressRead],
    summary="Update a delivery address",
)
async def update_address(
    address_id: UUID,
    data: AddressUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> ApiResponse[AddressRead]:
    address = await _service(session, user).update(address_id, data)
    return ok(AddressRead.model_validate(address), message="Address updated")


@router.delete(
    "/{address_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a delivery address",
)
async def delete_address(
    address_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_customer),
) -> Response:
    await _service(session, user).delete(address_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
