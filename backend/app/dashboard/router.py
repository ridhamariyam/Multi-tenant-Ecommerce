from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.dashboard.schemas import (
    DashboardOverviewResponse,
    SalesTrendItem,
    TopSellingProductItem,
)
from app.dashboard.service import DashboardService
from app.reports.service import ReportService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/dashboard", tags=["Admin-Dashboard"])


@router.get(
    "",
    response_model=ApiResponse[DashboardOverviewResponse],
    summary="Retrieve admin dashboard overview metrics",
)
async def get_dashboard_overview(
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.DASHBOARD_VIEW, legacy_staff=True)),
) -> ApiResponse[DashboardOverviewResponse]:
    service = DashboardService(session, user.tenant_id)
    data = await service.get_overview(currency=tenant.currency)

    reports = ReportService(session, user.tenant_id)
    today = datetime.now(timezone.utc).date()
    kpis = await reports.analytics(today - timedelta(days=29), today)
    data["insights"] = {
        "attention": await reports.attention(),
        "comparison": await reports.day_comparison(),
        "last_30_days": {
            key: kpis[key]
            for key in (
                "revenue",
                "orders",
                "average_order_value",
                "return_rate",
                "cancellation_rate",
                "cod_orders",
                "prepaid_orders",
                "cod_share_pct",
                "new_customers",
                "returning_customers",
            )
        },
    }
    return ok(data, message="Dashboard overview retrieved successfully")


@router.get(
    "/sales-trend",
    response_model=ApiResponse[list[SalesTrendItem]],
    summary="Retrieve aggregated daily sales trend",
)
async def get_sales_trend(
    days: int = Query(default=30, ge=1, le=365, description="Number of past days to aggregate"),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.DASHBOARD_VIEW, legacy_staff=True)),
) -> ApiResponse[list[SalesTrendItem]]:
    service = DashboardService(session, user.tenant_id)
    trend = await service.get_sales_trend(days=days)
    return ok(trend, message="Sales trend retrieved successfully")


@router.get(
    "/top-products",
    response_model=ApiResponse[list[TopSellingProductItem]],
    summary="Retrieve top selling products",
)
async def get_top_products(
    days: int = Query(default=30, ge=1, le=365, description="Time window in days"),
    limit: int = Query(default=10, ge=1, le=50, description="Max items to return"),
    session: AsyncSession = Depends(get_db),
    user: User = Depends(require_permission(Permission.DASHBOARD_VIEW, legacy_staff=True)),
) -> ApiResponse[list[TopSellingProductItem]]:
    service = DashboardService(session, user.tenant_id)
    products = await service.get_top_products(days=days, limit=limit)
    return ok(products, message="Top selling products retrieved successfully")