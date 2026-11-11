"""The dashboard's "top 10 selling products this week" (a rolling 7-day window)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.orders.constants import OrderStatus
from app.orders.models import OrderItem
from app.payments.constants import PaymentStatus
from tests.catalogue.factories import make_category, make_product, make_variant
from tests.dashboard.test_dashboard import TOP_PRODUCTS, _make_order


async def _sell(session, tenant, customer, variant, quantity, *, days_ago=0):
    order = await _make_order(
        session,
        tenant,
        customer,
        status=OrderStatus.DELIVERED,
        payment_status=PaymentStatus.PAID,
        created_at=datetime.now(timezone.utc) - timedelta(days=days_ago, hours=1 if days_ago else 0),
    )
    session.add(
        OrderItem(
            tenant_id=tenant.id,
            order_id=order.id,
            variant_id=variant["id"],
            product_id=variant["product_id"],
            product_name="x",
            variant_name=variant["name"],
            sku=variant["sku"],
            unit_price=Decimal("10.00"),
            quantity=quantity,
            subtotal=Decimal("10.00") * quantity,
        )
    )
    await session.commit()


async def test_top_ten_this_week_ranks_by_units_and_ignores_older_sales(
    client, admin_headers, session, tenant, make_user
):
    customer = await make_user(tenant=tenant)
    category = await make_category(client, admin_headers, name="Top Ten")
    variants = []
    for n in range(12):
        product = await make_product(client, admin_headers, category["id"], name=f"Product {n:02d}")
        variants.append(await make_variant(client, admin_headers, product["id"], sku=f"TOP-{n:02d}"))

    for n, variant in enumerate(variants[:11]):
        await _sell(session, tenant, customer, variant, quantity=n + 1)  # 1..11 units this week
    await _sell(session, tenant, customer, variants[11], quantity=100, days_ago=8)  # last week

    response = await client.get(TOP_PRODUCTS, params={"days": 7, "limit": 10}, headers=admin_headers)

    top = response.json()["data"]
    assert len(top) == 10
    assert [p["quantity_sold"] for p in top] == list(range(11, 1, -1))
    assert "Product 11" not in [p["product_name"] for p in top]


async def test_fewer_than_ten_sellers_are_all_shown(client, admin_headers, session, tenant, make_user, variant):
    customer = await make_user(tenant=tenant)
    await _sell(session, tenant, customer, variant, quantity=2)

    top = (await client.get(TOP_PRODUCTS, params={"days": 7, "limit": 10}, headers=admin_headers)).json()["data"]

    assert len(top) == 1
    assert top[0]["quantity_sold"] == 2
