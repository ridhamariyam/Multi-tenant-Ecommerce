"""Admin reports. Every report can also be downloaded: ?format=csv, xlsx or pdf."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.responses import ApiResponse, ok
from app.reports.exports import export_response
from app.reports.schemas import (
    AnalyticsReport,
    CategorySalesRow,
    CouponReportRow,
    CustomersQuery,
    CustomersReport,
    DateRange,
    InventoryQuery,
    InventoryRow,
    LocationQuery,
    LocationSalesRow,
    ProductSalesRow,
    ReturnsQuery,
    ReturnsReport,
    SalesQuery,
    SalesReport,
    UnsoldQuery,
    UnsoldRow,
)
from app.reports.service import ReportService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/reports", tags=["Admin-Reports"])

can_view = require_permission(Permission.REPORTS_VIEW)


def _period(params) -> str:
    return f"{params.start_date} to {params.end_date}"


def _name(kind: str, params) -> str:
    if hasattr(params, "start_date"):
        return f"{kind}-{params.start_date}-to-{params.end_date}"
    return kind


@router.get("/sales", response_model=ApiResponse[SalesReport], summary="Sales by day/week/month")
async def sales_report(
    tenant: CurrentTenant,
    params: Annotated[SalesQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    data = await ReportService(session, user.tenant_id).sales(
        params.start_date, params.end_date, params.group_by
    )
    if params.format != "json":
        return export_response(
            params.format, _name("sales", params), data["rows"],
            title=f"Sales by {params.group_by}", subtitle=_period(params),
        )
    return ok(SalesReport(**data, currency=tenant.currency), message="Sales report")


@router.get(
    "/sales-by-product",
    response_model=ApiResponse[list[ProductSalesRow]],
    summary="Units and sales per product",
)
async def sales_by_product(
    params: Annotated[DateRange, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).sales_by_product(
        params.start_date, params.end_date
    )
    if params.format != "json":
        return export_response(
            params.format, _name("sales-by-product", params), rows,
            title="Sales by product", subtitle=_period(params),
        )
    return ok([ProductSalesRow(**r) for r in rows], message="Sales by product")


@router.get(
    "/sales-by-category",
    response_model=ApiResponse[list[CategorySalesRow]],
    summary="Units and sales per category",
)
async def sales_by_category(
    params: Annotated[DateRange, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).sales_by_category(
        params.start_date, params.end_date
    )
    if params.format != "json":
        return export_response(
            params.format, _name("sales-by-category", params), rows,
            title="Sales by category", subtitle=_period(params),
        )
    return ok([CategorySalesRow(**r) for r in rows], message="Sales by category")


@router.get(
    "/sales-by-location",
    response_model=ApiResponse[list[LocationSalesRow]],
    summary="Orders and revenue per state (or city)",
)
async def sales_by_location(
    params: Annotated[LocationQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).sales_by_location(
        params.start_date, params.end_date, params.level
    )
    if params.format != "json":
        return export_response(
            params.format, _name("sales-by-location", params), rows,
            title=f"Sales by {params.level}", subtitle=_period(params),
        )
    return ok([LocationSalesRow(**r) for r in rows], message="Sales by location")


@router.get(
    "/inventory",
    response_model=ApiResponse[list[InventoryRow]],
    summary="Stock per variant; filter to low or out-of-stock",
)
async def inventory_report(
    params: Annotated[InventoryQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).inventory(params.stock_status)
    if params.format != "json":
        return export_response(
            params.format, f"inventory-{params.stock_status}", rows,
            title=f"Stock report ({params.stock_status})",
        )
    return ok([InventoryRow(**r) for r in rows], message="Inventory report")


@router.get(
    "/unsold",
    response_model=ApiResponse[list[UnsoldRow]],
    summary="Live products that have not sold in N days",
)
async def unsold_report(
    params: Annotated[UnsoldQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).unsold(params.days)
    if params.format != "json":
        return export_response(
            params.format, f"unsold-{params.days}-days", rows,
            title=f"Not sold in {params.days} days",
        )
    return ok([UnsoldRow(**r) for r in rows], message="Unsold products")


@router.get(
    "/customers",
    response_model=ApiResponse[CustomersReport],
    summary="New vs returning customers and top customers",
)
async def customers_report(
    params: Annotated[CustomersQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    data = await ReportService(session, user.tenant_id).customers(
        params.start_date, params.end_date, params.top
    )
    if params.format != "json":
        return export_response(
            params.format, _name("top-customers", params), data["top_customers"],
            title="Top customers", subtitle=_period(params),
        )
    return ok(CustomersReport(**data), message="Customer report")


@router.get(
    "/coupons",
    response_model=ApiResponse[list[CouponReportRow]],
    summary="Orders, discount and revenue per coupon",
)
async def coupons_report(
    params: Annotated[DateRange, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    rows = await ReportService(session, user.tenant_id).coupons(params.start_date, params.end_date)
    if params.format != "json":
        return export_response(
            params.format, _name("coupons", params), rows,
            title="Coupon report", subtitle=_period(params),
        )
    return ok([CouponReportRow(**r) for r in rows], message="Coupon report")


@router.get(
    "/returns",
    response_model=ApiResponse[ReturnsReport],
    summary="Undelivered returns (RTO) and cancellations",
)
async def returns_report(
    params: Annotated[ReturnsQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    data = await ReportService(session, user.tenant_id).returns(params.start_date, params.end_date)
    if params.format != "json":
        return export_response(
            params.format, _name(f"returns-by-{params.breakdown}", params),
            data[f"by_{params.breakdown}"],
            title=f"Returns by {params.breakdown}", subtitle=_period(params),
        )
    return ok(ReturnsReport(**data), message="Returns report")


@router.get(
    "/analytics",
    response_model=ApiResponse[AnalyticsReport],
    summary="Revenue, AOV, return rate, COD vs prepaid, customers, top products",
)
async def analytics_report(
    tenant: CurrentTenant,
    params: Annotated[DateRange, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
):
    data = await ReportService(session, user.tenant_id).analytics(
        params.start_date, params.end_date
    )
    if params.format != "json":
        return export_response(
            params.format, _name("product-performance", params), data["top_products"],
            title="Product performance", subtitle=_period(params),
        )
    return ok(AnalyticsReport(**data, currency=tenant.currency), message="Analytics")
