"""Admin dashboard API tests."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.dashboard.service import DEFAULT_LOW_STOCK_THRESHOLD, STOCK_SAMPLE_SIZE
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.payments.constants import PaymentStatus
from app.payments.models import Payment
from tests.helpers import load_data

DATA = load_data(__file__)

DASHBOARD = DATA["routes"]["dashboard"]
SALES_TREND = DATA["routes"]["sales_trend"]
TOP_PRODUCTS = DATA["routes"]["top_products"]


def _delivery_fields() -> dict:
    return DATA["order"]


async def _make_order(
    session: AsyncSession,
    tenant,
    customer,
    *,
    status: str,
    payment_status: str,
    created_at: datetime | None = None,
) -> Order:
    subtotal = Decimal("100.00")

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        status=status,
        payment_status=payment_status,
        subtotal=subtotal,
        shipping_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=subtotal,
        **_delivery_fields(),
    )

    if created_at is not None:
        order.created_at = created_at

    session.add(order)
    await session.flush()
    return order


@pytest.mark.asyncio
async def test_dashboard_authorization_guards(client: AsyncClient, customer_headers: dict):
    response = await client.get(DASHBOARD, headers=customer_headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_dashboard_overview_success(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
    variant,
    new_variant,
):
    customer = await make_user(tenant=tenant)
    low_stock_variant = await new_variant(initial_quantity=2, low_stock_threshold=5)

    order = await _make_order(
        session, tenant, customer, status=OrderStatus.PROCESSING, payment_status=PaymentStatus.PAID
    )
    item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        variant_id=variant["id"],
        product_id=variant["product_id"],
        product_name="Dashboard Widget",
        variant_name=variant["name"],
        sku=variant["sku"],
        unit_price=Decimal("100.00"),
        quantity=1,
        subtotal=Decimal("100.00"),
    )
    session.add(item)

    payment = Payment(
        tenant_id=tenant.id,
        order_id=order.id,
        amount=Decimal("100.00"),
        status=PaymentStatus.PAID,
    )
    session.add(payment)
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["sales"]["today"]["order_count"] >= 1
    assert Decimal(data["sales"]["today"]["revenue"]) >= Decimal("100.00")
    assert data["orders"]["total"] >= 1
    assert data["orders"]["today"] >= 1
    assert data["orders"]["processing"] >= 1
    assert data["products"]["total"] >= 1
    assert data["inventory"]["low_stock_count"] >= 1
    assert any(p["sku"] == low_stock_variant["sku"] for p in data["inventory"]["low_stock_variants"])
    assert data["payments"]["paid_count"] >= 1
    assert len(data["recent_orders"]) >= 1


@pytest.mark.asyncio
async def test_dashboard_counts_returned_orders_from_refunded_payments(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)

    order = await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.REFUNDED
    )
    payment = Payment(
        tenant_id=tenant.id,
        order_id=order.id,
        amount=Decimal("100.00"),
        status=PaymentStatus.REFUNDED,
    )
    session.add(payment)
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["orders"]["returned"] >= 1
    assert data["orders"]["total"] >= 1
    assert data["payments"]["refunded_count"] >= 1


@pytest.mark.asyncio
async def test_dashboard_sales_trend_and_top_products(
    client: AsyncClient,
    staff_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
    variant,
):
    customer = await make_user(tenant=tenant)

    order = await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    item = OrderItem(
        tenant_id=tenant.id,
        order_id=order.id,
        variant_id=variant["id"],
        product_id=variant["product_id"],
        product_name="Summer Dress",
        variant_name=variant["name"],
        sku=variant["sku"],
        unit_price=Decimal("50.00"),
        quantity=3,
        subtotal=Decimal("150.00"),
    )
    session.add(item)
    await session.commit()

    trend_res = await client.get(f"{SALES_TREND}?days=7", headers=staff_headers)
    assert trend_res.status_code == 200, trend_res.text
    assert len(trend_res.json()["data"]) >= 1

    top_res = await client.get(f"{TOP_PRODUCTS}?days=7&limit=5", headers=staff_headers)
    assert top_res.status_code == 200, top_res.text
    top_items = top_res.json()["data"]
    assert len(top_items) >= 1
    assert top_items[0]["product_name"] == "Summer Dress"
    assert top_items[0]["quantity_sold"] == 3


@pytest.mark.asyncio
async def test_todays_orders_counts_every_status_but_sales_today_stays_completed_only(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)

    await _make_order(
        session, tenant, customer, status=OrderStatus.PENDING, payment_status=PaymentStatus.PENDING
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    data = response.json()["data"]

    assert data["orders"]["today"] >= 1
    assert data["sales"]["today"]["order_count"] == 0


@pytest.mark.asyncio
async def test_week_over_week_comparison_calculates_counts_revenue_and_pct(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)
    now = datetime.now(timezone.utc)

    for _ in range(2):
        await _make_order(
            session,
            tenant,
            customer,
            status=OrderStatus.DELIVERED,
            payment_status=PaymentStatus.PAID,
            created_at=now - timedelta(days=2),
        )

    await _make_order(
        session,
        tenant,
        customer,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        created_at=now - timedelta(days=9),
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    week = response.json()["data"]["sales"]["week"]

    assert week["order_count"] >= 2
    assert week["previous_order_count"] >= 1
    assert Decimal(week["revenue"]) >= Decimal("200.00")
    assert Decimal(week["previous_revenue"]) >= Decimal("100.00")
    assert week["order_count_change_pct"] == round(
        (week["order_count"] - week["previous_order_count"]) / week["previous_order_count"] * 100.0, 2
    )
    assert week["revenue_change_pct"] == round(
        (float(week["revenue"]) - float(week["previous_revenue"]))
        / float(week["previous_revenue"])
        * 100.0,
        2,
    )


@pytest.mark.asyncio
async def test_inventory_overview_uses_variant_level_field_names(
    client: AsyncClient,
    admin_headers: dict,
    new_variant,
):
    low_stock_variant = await new_variant(initial_quantity=1, low_stock_threshold=5)
    out_of_stock_variant = await new_variant(initial_quantity=0, low_stock_threshold=5)

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    inventory = response.json()["data"]["inventory"]

    assert "low_stock_variants" in inventory
    assert "out_of_stock_variants" in inventory
    assert "low_stock_products" not in inventory
    assert "out_of_stock_products" not in inventory
    assert any(v["sku"] == low_stock_variant["sku"] for v in inventory["low_stock_variants"])
    assert any(v["sku"] == out_of_stock_variant["sku"] for v in inventory["out_of_stock_variants"])


@pytest.mark.asyncio
async def test_recent_orders_shows_customer_email_when_set(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant, email="shopper@example.com")
    await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    recent_orders = response.json()["data"]["recent_orders"]

    assert recent_orders[0]["customer_email"] == "shopper@example.com"


@pytest.mark.asyncio
async def test_recent_orders_customer_email_is_null_when_customer_has_no_email(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)
    await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    recent_orders = response.json()["data"]["recent_orders"]

    assert recent_orders[0]["customer_email"] is None


@pytest.mark.asyncio
async def test_change_pct_is_null_when_previous_period_is_zero(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)
    await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    today = response.json()["data"]["sales"]["today"]

    assert today["previous_order_count"] == 0
    assert Decimal(today["previous_revenue"]) == Decimal("0.00")
    assert today["order_count_change_pct"] is None
    assert today["revenue_change_pct"] is None


@pytest.mark.asyncio
async def test_change_pct_is_calculated_normally_when_previous_period_is_nonzero(
    client: AsyncClient,
    admin_headers: dict,
    session: AsyncSession,
    tenant,
    make_user,
):
    customer = await make_user(tenant=tenant)
    now = datetime.now(timezone.utc)

    yesterday_noon = datetime.combine(now.date() - timedelta(days=1), time(12, 0), tzinfo=timezone.utc)
    await _make_order(
        session,
        tenant,
        customer,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        created_at=yesterday_noon,
    )
    await _make_order(
        session, tenant, customer, status=OrderStatus.DELIVERED, payment_status=PaymentStatus.PAID
    )
    await session.commit()

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    today = response.json()["data"]["sales"]["today"]

    assert today["previous_order_count"] == 1
    assert today["order_count_change_pct"] == 0.0
    assert today["revenue_change_pct"] == 0.0

@pytest.mark.asyncio
async def test_an_unset_threshold_falls_back_to_the_default(
    client: AsyncClient, admin_headers: dict, new_variant
):
    """The column is NOT NULL default 0, so 0 is what "unset" looks like."""
    sparse = await new_variant(initial_quantity=4, low_stock_threshold=0)

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    inventory = response.json()["data"]["inventory"]

    listed = [v for v in inventory["low_stock_variants"] if v["sku"] == sparse["sku"]]
    assert listed, inventory["low_stock_variants"]
    assert listed[0]["low_stock_threshold"] == DEFAULT_LOW_STOCK_THRESHOLD


@pytest.mark.asyncio
async def test_an_explicit_threshold_is_respected(
    client: AsyncClient, admin_headers: dict, new_variant
):
    plenty = await new_variant(initial_quantity=4, low_stock_threshold=2)

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    inventory = response.json()["data"]["inventory"]

    assert all(v["sku"] != plenty["sku"] for v in inventory["low_stock_variants"])


@pytest.mark.asyncio
async def test_stock_counts_are_complete_but_the_sample_is_capped(
    client: AsyncClient, admin_headers: dict, new_variant
):
    """Counts come from SQL, so they are not limited to the ten shown."""
    empty = STOCK_SAMPLE_SIZE + 2
    for _ in range(empty):
        await new_variant(initial_quantity=0)

    response = await client.get(DASHBOARD, headers=admin_headers)
    assert response.status_code == 200, response.text
    inventory = response.json()["data"]["inventory"]

    assert inventory["out_of_stock_count"] >= empty
    assert len(inventory["out_of_stock_variants"]) == STOCK_SAMPLE_SIZE


@pytest.mark.asyncio
async def test_the_dashboard_never_reports_another_tenants_stock(
    other_client: AsyncClient, other_admin_headers: dict, admin_headers, new_variant
):
    await new_variant(initial_quantity=0)

    response = await other_client.get(DASHBOARD, headers=other_admin_headers)

    assert response.status_code == 200, response.text
    inventory = response.json()["data"]["inventory"]
    assert inventory["out_of_stock_count"] == 0
    assert inventory["out_of_stock_variants"] == []
    assert response.json()["data"]["products"]["total"] == 0
