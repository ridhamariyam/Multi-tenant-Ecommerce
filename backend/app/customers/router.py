from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.addresses.schemas import AddressRead
from app.audit.service import record_activity
from app.auth.dependencies import require_permission
from app.auth.permissions import Permission
from app.core.database import get_db
from app.core.pagination import PageParams
from app.core.responses import ApiResponse, ok, paginated
from app.customers.schemas import (
    CustomerBlockUpdate,
    CustomerDetail,
    CustomerNoteCreate,
    CustomerNoteRead,
    CustomerQuery,
    CustomerSummary,
    CustomerTagsUpdate,
)
from app.customers.service import CustomerService
from app.orders.schemas import OrderSummaryRead
from app.orders.serializers import order_summary_read
from app.orders.service import OrderService
from app.tenants.resolver import CurrentTenant
from app.users.models import User

router = APIRouter(prefix="/admin/customers", tags=["Admin-Customers"])

can_view = require_permission(Permission.CUSTOMERS_VIEW)
can_manage = require_permission(Permission.CUSTOMERS_MANAGE)


@router.get("", response_model=ApiResponse[list[CustomerSummary]], summary="List customers")
async def list_customers(
    params: Annotated[CustomerQuery, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
) -> ApiResponse[list[CustomerSummary]]:
    rows, total = await CustomerService(session, user.tenant_id).list(params)
    return paginated(
        [CustomerSummary(**row) for row in rows],
        total_items=total,
        params=params,
        message="Customers retrieved",
    )


@router.get("/tags", response_model=ApiResponse[list[str]], summary="Customer tags in use")
async def list_customer_tags(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
) -> ApiResponse[list[str]]:
    return ok(await CustomerService(session, user.tenant_id).all_tags(), message="Tags")


@router.get(
    "/{customer_id}",
    response_model=ApiResponse[CustomerDetail],
    summary="A customer's profile, totals, addresses, tags and notes",
)
async def get_customer(
    customer_id: UUID,
    tenant: CurrentTenant,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
) -> ApiResponse[CustomerDetail]:
    detail = await CustomerService(session, user.tenant_id).get(customer_id)
    detail["addresses"] = [AddressRead.model_validate(a) for a in detail["addresses"]]
    detail["notes"] = [CustomerNoteRead.model_validate(n) for n in detail["notes"]]
    return ok(CustomerDetail(**detail, currency=tenant.currency), message="Customer retrieved")


@router.get(
    "/{customer_id}/orders",
    response_model=ApiResponse[list[OrderSummaryRead]],
    summary="A customer's order history",
)
async def customer_orders(
    customer_id: UUID,
    tenant: CurrentTenant,
    params: Annotated[PageParams, Query()],
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_view),
) -> ApiResponse[list[OrderSummaryRead]]:
    await CustomerService(session, user.tenant_id).require(customer_id)
    orders, total = await OrderService(session, user.tenant_id).list(
        params, customer_id=customer_id
    )
    return paginated(
        [order_summary_read(o, tenant.currency) for o in orders],
        total_items=total,
        params=params,
        message="Orders retrieved",
    )


@router.put(
    "/{customer_id}/tags",
    response_model=ApiResponse[list[str]],
    summary="Replace a customer's tags",
)
async def set_customer_tags(
    customer_id: UUID,
    data: CustomerTagsUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[list[str]]:
    customer = await CustomerService(session, user.tenant_id).set_tags(customer_id, data.tags)
    await record_activity(
        session,
        user,
        "customer.tags_set",
        "customer",
        customer_id,
        summary=f"Tags: {', '.join(data.tags) or '(none)'}",
        changes=data.model_dump(),
        request=request,
    )
    return ok(customer.tags or [], message="Tags updated")


@router.put(
    "/{customer_id}/order-block",
    response_model=ApiResponse[CustomerSummary],
    summary="Block or unblock a customer from placing new orders",
)
async def set_order_block(
    customer_id: UUID,
    data: CustomerBlockUpdate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[CustomerSummary]:
    service = CustomerService(session, user.tenant_id)
    await service.set_order_block(customer_id, data.blocked, data.reason)
    await record_activity(
        session,
        user,
        "customer.order_blocked" if data.blocked else "customer.order_unblocked",
        "customer",
        customer_id,
        summary=("Blocked from ordering" if data.blocked else "Allowed to order again")
        + (f": {data.reason}" if data.blocked and data.reason else ""),
        changes=data.model_dump(),
        request=request,
    )
    detail = await service.get(customer_id)
    return ok(
        CustomerSummary(**{k: detail[k] for k in CustomerSummary.model_fields}),
        message="Customer blocked" if data.blocked else "Customer unblocked",
    )


@router.post(
    "/{customer_id}/notes",
    response_model=ApiResponse[CustomerNoteRead],
    status_code=status.HTTP_201_CREATED,
    summary="Add a staff note to a customer",
)
async def add_customer_note(
    customer_id: UUID,
    data: CustomerNoteCreate,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> ApiResponse[CustomerNoteRead]:
    note = await CustomerService(session, user.tenant_id).add_note(customer_id, user, data.body)
    await record_activity(
        session,
        user,
        "customer.note_added",
        "customer",
        customer_id,
        summary="Added a note",
        request=request,
    )
    return ok(CustomerNoteRead.model_validate(note), message="Note added")


@router.delete(
    "/{customer_id}/notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a staff note",
)
async def delete_customer_note(
    customer_id: UUID,
    note_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(can_manage),
) -> Response:
    await CustomerService(session, user.tenant_id).delete_note(customer_id, note_id)
    await record_activity(
        session,
        user,
        "customer.note_deleted",
        "customer",
        customer_id,
        summary="Deleted a note",
        changes={"note_id": str(note_id)},
        request=request,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
