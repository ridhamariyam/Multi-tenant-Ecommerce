from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit.dependencies import AUDITED
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.cod.models import CodBlacklistEntry, CodSettings
from app.cod.schemas import (
    BlacklistCreate,
    BlacklistQuery,
    BlacklistRead,
    CodReportQuery,
    CodReportRead,
    CodSettingsRead,
    CodSettingsUpdate,
    CollectionQuery,
    CollectionRow,
    RemittanceCreate,
    RemittanceResult,
)
from app.cod.service import CodService
from app.core.database import get_db
from app.core.responses import ApiResponse, ok, paginated
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/cod", tags=["Admin-COD"], dependencies=AUDITED)


def _settings_read(settings: CodSettings | None) -> CodSettingsRead:
    if settings is None:
        return CodSettingsRead()
    return CodSettingsRead(
        is_enabled=settings.is_enabled,
        min_order_amount=settings.min_order_amount,
        max_order_amount=settings.max_order_amount,
        fee_amount=settings.fee_amount,
        advance_amount=settings.advance_amount,
        auto_blacklist_threshold=settings.auto_blacklist_threshold,
    )


def _entry_read(entry: CodBlacklistEntry) -> BlacklistRead:
    return BlacklistRead(
        id=entry.id,
        phone=entry.phone,
        reason=entry.reason,
        source=entry.source,
        created_at=entry.created_at,
    )


@router.get("/settings", response_model=ApiResponse[CodSettingsRead], summary="View COD rules")
async def get_cod_settings(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[CodSettingsRead]:
    settings = await CodService(session, user.tenant_id).get_settings()
    return ok(_settings_read(settings), message="COD settings retrieved")


@router.put(
    "/settings",
    response_model=ApiResponse[CodSettingsRead],
    summary="Set the COD switch, order limits, fee, advance and auto-blacklist rule",
)
async def update_cod_settings(
    data: CodSettingsUpdate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[CodSettingsRead]:
    settings = await CodService(session, user.tenant_id).update_settings(data)
    return ok(_settings_read(settings), message="COD settings updated")


@router.get(
    "/blacklist",
    response_model=ApiResponse[list[BlacklistRead]],
    summary="Phone numbers blocked from COD",
)
async def list_blacklist(
    params: Annotated[BlacklistQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[BlacklistRead]]:
    entries, total = await CodService(session, user.tenant_id).list_blacklist(
        params, source=params.source
    )
    return paginated(
        [_entry_read(entry) for entry in entries],
        total_items=total,
        params=params,
        message="COD blacklist retrieved",
    )


@router.post(
    "/blacklist",
    response_model=ApiResponse[BlacklistRead],
    status_code=status.HTTP_201_CREATED,
    summary="Block a phone number from COD",
)
async def add_to_blacklist(
    data: BlacklistCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> ApiResponse[BlacklistRead]:
    entry = await CodService(session, user.tenant_id).add_to_blacklist(data)
    return ok(_entry_read(entry), message="Phone blocked from COD")


@router.delete(
    "/blacklist/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Unblock a phone number",
)
async def remove_from_blacklist(
    entry_id: UUID,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.SETTINGS_MANAGE)),
) -> Response:
    await CodService(session, user.tenant_id).remove_from_blacklist(entry_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/report",
    response_model=ApiResponse[CodReportRead],
    summary="COD orders, delivery rate and money collected for a date range",
)
async def cod_report(
    tenant: CurrentTenant,
    params: Annotated[CodReportQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.REPORTS_VIEW)),
) -> ApiResponse[CodReportRead]:
    report = await CodService(session, user.tenant_id).report(params.start_date, params.end_date)
    return ok(CodReportRead(**report, currency=tenant.currency), message="COD report")


@router.get(
    "/collections",
    response_model=ApiResponse[list[CollectionRow]],
    summary="Collected COD cash, outstanding or already remitted by the courier",
)
async def list_collections(
    params: Annotated[CollectionQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_VIEW, legacy_staff=True)),
) -> ApiResponse[list[CollectionRow]]:
    rows, total = await CodService(session, user.tenant_id).collections(
        params, remitted=params.status == "remitted"
    )
    return paginated(
        [CollectionRow(**row) for row in rows],
        total_items=total,
        params=params,
        message="COD collections retrieved",
    )


@router.post(
    "/remittances",
    response_model=ApiResponse[RemittanceResult],
    summary="Record that the courier paid over collected COD cash",
)
async def record_remittance(
    data: RemittanceCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.PAYMENTS_MANAGE)),
) -> ApiResponse[RemittanceResult]:
    result = await CodService(session, user.tenant_id).record_remittance(
        data.payment_ids, data.reference, data.remitted_on
    )
    return ok(RemittanceResult(**result), message="Remittance recorded")
