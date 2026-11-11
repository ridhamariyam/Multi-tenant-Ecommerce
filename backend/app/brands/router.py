"""Brands a merchant account belongs to, reached with the platform session."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.brands.schemas import (
    BrandMembershipRead,
    BrandRead,
    BrandRegister,
    BrandRegistered,
    BrandToken,
    BrandUpdate,
    MemberCreate,
    MemberRead,
    MemberUpdate,
)
from app.brands.service import BrandService
from app.core import rate_limit
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.merchants.dependencies import CurrentAccount

router = APIRouter(prefix="/brands", tags=["Brands"])


@router.post(
    "/register",
    response_model=ApiResponse[BrandRegistered],
    status_code=status.HTTP_201_CREATED,
    summary="Create a brand owned by the signed-in account, with its store",
)
async def register_brand(
    data: BrandRegister,
    account: CurrentAccount,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BrandRegistered]:
    settings = get_settings()
    await rate_limit.enforce(
        "brand-register",
        str(account.id),
        limit=settings.brand_registration_rate_limit_attempts,
        window_seconds=settings.brand_registration_rate_limit_window_seconds,
    )
    return ok(await BrandService(session, account).register(data), message="Brand created")


@router.get(
    "/me",
    response_model=ApiResponse[list[BrandMembershipRead]],
    summary="Brands the signed-in account belongs to",
)
async def my_brands(
    account: CurrentAccount, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[BrandMembershipRead]]:
    return ok(await BrandService(session, account).memberships(), message="Brands")


@router.get("/{brand_id}", response_model=ApiResponse[BrandRead], summary="One of your brands")
async def get_brand(
    brand_id: UUID, account: CurrentAccount, session: AsyncSession = Depends(get_db)
) -> ApiResponse[BrandRead]:
    return ok(BrandRead.model_validate(await BrandService(session, account).get(brand_id)), message="Brand")


@router.put("/{brand_id}", response_model=ApiResponse[BrandRead], summary="Change a brand's profile")
async def update_brand(
    brand_id: UUID,
    data: BrandUpdate,
    account: CurrentAccount,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[BrandRead]:
    tenant = await BrandService(session, account).update(brand_id, data)
    return ok(BrandRead.model_validate(tenant), message="Brand updated")


@router.post(
    "/{brand_id}/switch",
    response_model=ApiResponse[BrandToken],
    summary="A token for working in one of your brands",
)
async def switch_brand(
    brand_id: UUID, account: CurrentAccount, session: AsyncSession = Depends(get_db)
) -> ApiResponse[BrandToken]:
    return ok(await BrandService(session, account).switch(brand_id), message="Brand selected")


@router.get(
    "/{brand_id}/members", response_model=ApiResponse[list[MemberRead]], summary="A brand's members"
)
async def list_members(
    brand_id: UUID, account: CurrentAccount, session: AsyncSession = Depends(get_db)
) -> ApiResponse[list[MemberRead]]:
    return ok(await BrandService(session, account).list_members(brand_id), message="Members")


@router.post(
    "/{brand_id}/members",
    response_model=ApiResponse[MemberRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add an existing merchant account to a brand",
)
async def add_member(
    brand_id: UUID,
    data: MemberCreate,
    account: CurrentAccount,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[MemberRead]:
    return ok(await BrandService(session, account).add_member(brand_id, data), message="Member added")


@router.patch(
    "/{brand_id}/members/{member_id}",
    response_model=ApiResponse[MemberRead],
    summary="Change a member's role, or remove them",
)
async def update_member(
    brand_id: UUID,
    member_id: UUID,
    data: MemberUpdate,
    account: CurrentAccount,
    session: AsyncSession = Depends(get_db),
) -> ApiResponse[MemberRead]:
    member = await BrandService(session, account).update_member(brand_id, member_id, data)
    return ok(member, message="Member updated")
