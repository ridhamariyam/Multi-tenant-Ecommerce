from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.coupons.models import Coupon, CouponUsage
from app.coupons.repository import CouponRepository
from app.orders.models import Order
from tests.catalogue.factories import inventory_url
from tests.conftest import headers_for
from tests.helpers import run_concurrently, succeeded
from tests.orders.conftest import CHECKOUT


async def _make_coupon(session: AsyncSession, tenant, **overrides) -> Coupon:
    repo = CouponRepository(session, tenant.id)
    defaults = dict(
        tenant_id=tenant.id,
        code="ORD-TEST",
        discount_type="FIXED_AMOUNT",
        discount_value=Decimal("100.00"),
        is_active=True,
    )
    defaults.update(overrides)
    coupon = Coupon(**defaults)
    await repo.add(coupon)
    await session.commit()
    return coupon


# --------------------------------- checkout preview ---------------------------------


async def test_preview_without_coupon_is_unchanged(
    client, customer_auth, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 2)
    response = await preview_checkout(customer_auth)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["coupon_code"] is None
    assert body["discount_amount"] == "0.00"
    assert body["total_amount"] == body["subtotal"]


async def test_preview_with_valid_coupon_shows_discount_and_updated_total(
    client, customer_auth, session, tenant, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 2)  # subtotal 1998.00
    await _make_coupon(session, tenant, code="SAVE100", discount_value=Decimal("100.00"))

    response = await preview_checkout(customer_auth, "save100")

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["coupon_code"] == "SAVE100"
    assert body["discount_amount"] == "100.00"
    assert Decimal(body["total_amount"]) == Decimal(body["subtotal"]) - Decimal("100.00") + Decimal(
        body["shipping_amount"]
    ) + Decimal(body["tax_amount"])


async def test_preview_with_invalid_coupon_fails(
    client, customer_auth, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 1)
    response = await preview_checkout(customer_auth, "NOPE")
    assert response.status_code == 404


async def test_preview_with_expired_coupon_fails(
    client, customer_auth, session, tenant, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 1)
    past = datetime.now(timezone.utc) - timedelta(days=1)
    await _make_coupon(session, tenant, code="EXPIRED1", expires_at=past)

    response = await preview_checkout(customer_auth, "EXPIRED1")
    assert response.status_code == 400


async def test_preview_with_inactive_coupon_fails(
    client, customer_auth, session, tenant, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 1)
    await _make_coupon(session, tenant, code="INACTIVE9", is_active=False)

    response = await preview_checkout(customer_auth, "INACTIVE9")
    assert response.status_code == 404


async def test_preview_does_not_consume_the_coupon(
    client, customer_auth, session, tenant, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 1)
    coupon = await _make_coupon(session, tenant, code="STILLFRESH", usage_limit=1)

    for _ in range(3):
        response = await preview_checkout(customer_auth, "STILLFRESH")
        assert response.status_code == 200, response.text

    await session.refresh(coupon)
    assert coupon.times_used == 0
    usages = (await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))).all()
    assert usages == []


# --------------------------------- order placement ---------------------------------


async def test_place_order_without_coupon_is_unchanged(
    client, customer_auth, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 2)
    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["coupon_code"] is None
    assert body["discount_amount"] == "0.00"
    assert body["total_amount"] == body["subtotal"]


async def test_place_order_with_valid_coupon_applies_discount(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 2)  # 1998.00
    await _make_coupon(session, tenant, code="ORDER50", discount_value=Decimal("50.00"))

    response = await place_order(customer_auth, address["id"], "order50")

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["coupon_code"] == "ORDER50"
    assert body["discount_amount"] == "50.00"
    assert Decimal(body["total_amount"]) == Decimal(body["subtotal"]) - Decimal("50.00") + Decimal(
        body["shipping_amount"]
    ) + Decimal(body["tax_amount"])


async def test_place_order_stores_coupon_snapshot(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    coupon = await _make_coupon(session, tenant, code="SNAPSHOT1", discount_value=Decimal("75.00"))
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await place_order(customer_auth, address["id"], "SNAPSHOT1")
    assert response.status_code == 201, response.text
    order_id = response.json()["data"]["id"]

    row = await session.get(Order, UUID(order_id))
    assert row.coupon_id == coupon.id
    assert row.coupon_code == "SNAPSHOT1"
    assert row.discount_amount == Decimal("75.00")


async def test_historical_order_discount_survives_coupon_deactivation(
    client, admin_headers, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    coupon = await _make_coupon(session, tenant, code="LATERDEAD", discount_value=Decimal("30.00"))
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await place_order(customer_auth, address["id"], "LATERDEAD")
    assert response.status_code == 201, response.text
    order_id = response.json()["data"]["id"]

    delete_response = await client.delete(f"/api/v1/admin/coupons/{coupon.id}", headers=admin_headers)
    assert delete_response.status_code == 200

    order_response = await client.get(f"/api/v1/orders/{order_id}", headers=customer_auth)
    assert order_response.status_code == 200
    body = order_response.json()["data"]
    assert body["coupon_code"] == "LATERDEAD"
    assert body["discount_amount"] == "30.00"


async def test_successful_order_creates_exactly_one_coupon_usage_and_increments_times_used(
    client, customer_auth, customer, session, tenant, address, variant, add_to_cart, place_order
):
    coupon = await _make_coupon(session, tenant, code="ONCEONLY", discount_value=Decimal("20.00"))
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"], "ONCEONLY")
    assert response.status_code == 201, response.text

    await session.refresh(coupon)
    assert coupon.times_used == 1

    usages = (await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))).all()
    assert len(usages) == 1
    assert usages[0].customer_id == customer.id
    assert usages[0].discount_amount == Decimal("20.00")


async def test_invalid_coupon_blocks_order_and_leaves_no_trace(
    client, customer_auth, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 1)
    response = await place_order(customer_auth, address["id"], "GHOSTCODE")
    assert response.status_code == 404

    listing = await client.get("/api/v1/orders", headers=customer_auth)
    assert listing.json()["data"] == []


async def test_expired_coupon_blocks_order_without_consuming_it(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    coupon = await _make_coupon(session, tenant, code="EXPIREDORD", expires_at=past)
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"], "EXPIREDORD")
    assert response.status_code == 400

    await session.refresh(coupon)
    assert coupon.times_used == 0


async def test_minimum_order_amount_blocks_order(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    await _make_coupon(
        session, tenant, code="MINORDER1", min_order_amount=Decimal("5000.00")
    )
    await add_to_cart(customer_auth, variant["id"], 1)  # 999.00, below minimum

    response = await place_order(customer_auth, address["id"], "MINORDER1")
    assert response.status_code == 400


async def test_stock_failure_does_not_consume_coupon(
    client, admin_headers, customer_auth, session, tenant, address, new_variant, add_to_cart, place_order
):
    variant = await new_variant(initial_quantity=5)
    coupon = await _make_coupon(session, tenant, code="STOCKFAIL", discount_value=Decimal("10.00"))
    await add_to_cart(customer_auth, variant["id"], 5)

    await client.put(
        inventory_url(variant["id"]), json={"available_quantity": 0}, headers=admin_headers
    )

    response = await place_order(customer_auth, address["id"], "STOCKFAIL")
    assert response.status_code == 409

    await session.refresh(coupon)
    assert coupon.times_used == 0
    usages = (await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))).all()
    assert usages == []


async def test_deactivated_coupon_cannot_be_used_for_a_new_order(
    client, admin_headers, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    coupon = await _make_coupon(session, tenant, code="DEADBEFORE")
    delete_response = await client.delete(f"/api/v1/admin/coupons/{coupon.id}", headers=admin_headers)
    assert delete_response.status_code == 200

    await add_to_cart(customer_auth, variant["id"], 1)
    response = await place_order(customer_auth, address["id"], "DEADBEFORE")
    assert response.status_code == 404


async def test_coupon_from_another_tenant_cannot_be_used(
    client, customer_auth, session, tenant, other_tenant, address, variant, add_to_cart, place_order
):
    await _make_coupon(session, other_tenant, code="FOREIGNCODE")
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"], "FOREIGNCODE")
    assert response.status_code == 404


async def test_client_cannot_supply_pricing_fields(
    client, customer_auth, address, variant, add_to_cart
):
    """CheckoutCreate carries address_id and coupon_code only. Pricing is the
    server's to compute, and a payload reaching for it is refused outright."""
    await add_to_cart(customer_auth, variant["id"], 2)

    rejected = await client.post(
        CHECKOUT,
        json={
            "address_id": str(address["id"]),
            "subtotal": "1.00",
            "discount_amount": "999.00",
            "total_amount": "0.01",
        },
        headers=customer_auth,
    )
    assert rejected.status_code == 422, rejected.text
    refused = {detail["field"] for detail in rejected.json()["error"]["details"]}
    assert refused == {"subtotal", "discount_amount", "total_amount"}

    # The same cart, priced by the server alone.
    accepted = await client.post(
        CHECKOUT, json={"address_id": str(address["id"])}, headers=customer_auth
    )
    assert accepted.status_code == 201, accepted.text
    body = accepted.json()["data"]
    assert body["subtotal"] == "1998.00"
    assert body["discount_amount"] == "0.00"


# ----------------------------------- usage limits -----------------------------------


async def test_global_usage_limit_blocks_a_second_order(
    client, customer_auth, session, tenant, address, new_variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="GLOBALONE", usage_limit=1)

    v1 = await new_variant()
    await add_to_cart(customer_auth, v1["id"], 1)
    first = await place_order(customer_auth, address["id"], "GLOBALONE")
    assert first.status_code == 201, first.text

    v2 = await new_variant()
    await add_to_cart(customer_auth, v2["id"], 1)
    second = await place_order(customer_auth, address["id"], "GLOBALONE")
    assert second.status_code == 400


async def test_per_customer_usage_limit_blocks_repeat_use_by_the_same_customer(
    client, customer_auth, session, tenant, address, new_variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="ONCEPERSON", per_customer_usage_limit=1)

    v1 = await new_variant()
    await add_to_cart(customer_auth, v1["id"], 1)
    first = await place_order(customer_auth, address["id"], "ONCEPERSON")
    assert first.status_code == 201, first.text

    v2 = await new_variant()
    await add_to_cart(customer_auth, v2["id"], 1)
    second = await place_order(customer_auth, address["id"], "ONCEPERSON")
    assert second.status_code == 400


async def test_per_customer_limit_does_not_block_a_different_customer(
    client, customer_auth, session, tenant, make_user, address, save_address, new_variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="SHAREDCODE", per_customer_usage_limit=1)

    v1 = await new_variant()
    await add_to_cart(customer_auth, v1["id"], 1)
    first = await place_order(customer_auth, address["id"], "SHAREDCODE")
    assert first.status_code == 201, first.text

    other = await make_user(tenant=tenant, phone="+919822229101")
    other_headers = headers_for(other)
    other_address = await save_address(other_headers)
    v2 = await new_variant()
    await add_to_cart(other_headers, v2["id"], 1)
    second = await place_order(other_headers, other_address["id"], "SHAREDCODE")
    assert second.status_code == 201, second.text


async def test_concurrent_orders_cannot_exceed_the_global_usage_limit(
    engine, session, tenant, make_user, client, save_address, new_variant, add_to_cart,
):
    """Two customers race for a coupon with usage_limit=1 -- exactly one order
    may successfully redeem it."""
    await _make_coupon(session, tenant, code="RACECOUPON", usage_limit=1, discount_value=Decimal("10.00"))

    racers = []
    for i in range(2):
        user = await make_user(tenant=tenant, phone=f"+91982222920{i}")
        headers = headers_for(user)
        variant = await new_variant()
        await add_to_cart(headers, variant["id"], 1)
        addr = await save_address(headers)
        racers.append((user, addr))

    async def checkout(db, index):
        from app.orders.service import CheckoutService

        user, addr = racers[index]
        return await CheckoutService(db, tenant.id, user.id).place_order(
            UUID(addr["id"]), "RACECOUPON"
        )

    results = await run_concurrently(engine, 2, checkout)
    assert len(succeeded(results)) == 1

    coupon = await CouponRepository(session, tenant.id).get_by_code("RACECOUPON")
    await session.refresh(coupon)
    assert coupon.times_used == 1

    usages = (await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))).all()
    assert len(usages) == 1


async def test_concurrent_automatic_coupon_redemption_refreshes_usage_limit(
    engine,
    session,
    tenant,
    make_user,
    save_address,
    new_variant,
    add_to_cart,
    monkeypatch,
):
    """A stale automatic-coupon candidate cannot pass the cap after waiting on its lock."""
    import asyncio

    from app.coupons.service import CouponService
    from app.orders.service import CheckoutService

    coupon = await _make_coupon(
        session,
        tenant,
        code="AUTO-RACE",
        usage_limit=1,
        is_automatic=True,
        discount_value=Decimal("10.00"),
    )

    racers = []
    for i in range(2):
        user = await make_user(tenant=tenant, phone=f"+91982222930{i}")
        headers = headers_for(user)
        variant = await new_variant()
        await add_to_cart(headers, variant["id"], 1)
        address = await save_address(headers)
        racers.append((user, address))

    # Force both checkouts to load and evaluate the automatic candidate before
    # either is allowed to acquire the coupon lock.
    ready = asyncio.Event()
    arrivals = 0
    original = CouponService.best_automatic

    async def synchronized_candidates(self, *args, **kwargs):
        nonlocal arrivals
        result = await original(self, *args, **kwargs)
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await ready.wait()
        return result

    monkeypatch.setattr(CouponService, "best_automatic", synchronized_candidates)

    async def checkout(db, index):
        user, address = racers[index]
        return await CheckoutService(db, tenant.id, user.id).place_order(
            UUID(address["id"])
        )

    results = await run_concurrently(engine, 2, checkout)
    orders = succeeded(results)
    assert len(orders) == 2
    assert sum(order.coupon_code == "AUTO-RACE" for order in orders) == 1

    await session.refresh(coupon)
    assert coupon.times_used == 1
    usages = (
        await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))
    ).all()
    assert len(usages) == 1


async def test_duplicate_redemption_for_the_same_order_is_prevented(
    session, tenant, make_user
):
    """CouponUsage's (tenant_id, order_id) unique constraint is the backstop
    even if something tried to redeem twice for one order."""
    from uuid import uuid4
    
    from app.coupons.service import CouponService
    from app.orders.constants import OrderStatus
    from app.payments.constants import PaymentStatus
   

    customer = await make_user(tenant=tenant, phone="+919822229201")
    coupon = await _make_coupon(session, tenant, code="ONEORDERONLY")

    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        status=OrderStatus.PENDING.value,
        payment_status=PaymentStatus.PENDING.value,
        subtotal=Decimal("300.00"),
        discount_amount=Decimal("0.00"),
        shipping_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("300.00"),
        delivery_name="Test",
        delivery_phone="+919876500009",
        delivery_address_line_1="1 Test Street",
        delivery_city="Testville",
        delivery_state="TS",
        delivery_postal_code="100001",
        delivery_country="IN",
    )
    session.add(order)
    await session.commit()

    service = CouponService(session, tenant.id)
    await service.record_usage(coupon.id, customer.id, order.id, Decimal("10.00"))

    with pytest.raises(IntegrityError):
        await service.record_usage(coupon.id, customer.id, order.id, Decimal("10.00"))


# ------------------------------ unlimited (NULL) usage limits ------------------------------


async def test_both_limits_null_means_fully_unlimited(
    client, customer_auth, session, tenant, make_user, address, save_address, new_variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="UNLIMITED1", usage_limit=None, per_customer_usage_limit=None)

    for i in range(3):
        user = await make_user(tenant=tenant, phone=f"+91982222930{i}")
        headers = headers_for(user)
        addr = await save_address(headers)
        variant = await new_variant()
        await add_to_cart(headers, variant["id"], 1)
        response = await place_order(headers, addr["id"], "UNLIMITED1")
        assert response.status_code == 201, response.text


async def test_global_limit_set_per_customer_null_allows_repeat_use_by_one_customer(
    client, customer_auth, session, tenant, address, new_variant, add_to_cart, place_order
):
    await _make_coupon(
        session, tenant, code="GLOBALCAP5", usage_limit=5, per_customer_usage_limit=None
    )

    for _ in range(2):
        variant = await new_variant()
        await add_to_cart(customer_auth, variant["id"], 1)
        response = await place_order(customer_auth, address["id"], "GLOBALCAP5")
        assert response.status_code == 201, response.text


async def test_global_null_per_customer_limit_set(
    client, customer_auth, session, tenant, address, new_variant, add_to_cart, place_order
):
    await _make_coupon(
        session, tenant, code="PERCUST2", usage_limit=None, per_customer_usage_limit=2
    )

    for _ in range(2):
        variant = await new_variant()
        await add_to_cart(customer_auth, variant["id"], 1)
        response = await place_order(customer_auth, address["id"], "PERCUST2")
        assert response.status_code == 201, response.text

    variant = await new_variant()
    await add_to_cart(customer_auth, variant["id"], 1)
    third = await place_order(customer_auth, address["id"], "PERCUST2")
    assert third.status_code == 400


async def test_both_limits_set(
    client, customer_auth, session, tenant, make_user, address, save_address, new_variant, add_to_cart, place_order
):
    """usage_limit=3, per_customer_usage_limit=1: three different customers
    each succeed once; a fourth customer is blocked by the global cap even
    though their own per-customer count is still zero."""
    await _make_coupon(session, tenant, code="BOTHLIMITS", usage_limit=3, per_customer_usage_limit=1)

    for i in range(3):
        user = await make_user(tenant=tenant, phone=f"+91982222940{i}")
        headers = headers_for(user)
        addr = await save_address(headers)
        variant = await new_variant()
        await add_to_cart(headers, variant["id"], 1)
        response = await place_order(headers, addr["id"], "BOTHLIMITS")
        assert response.status_code == 201, response.text

    fourth_user = await make_user(tenant=tenant, phone="+919822229499")
    fourth_headers = headers_for(fourth_user)
    fourth_addr = await save_address(fourth_headers)
    variant = await new_variant()
    await add_to_cart(fourth_headers, variant["id"], 1)
    fourth = await place_order(fourth_headers, fourth_addr["id"], "BOTHLIMITS")
    assert fourth.status_code == 400


async def test_zero_usage_limit_is_not_treated_as_unlimited(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="ZEROLIMIT", usage_limit=0)
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"], "ZEROLIMIT")
    assert response.status_code == 400


async def test_zero_per_customer_limit_is_not_treated_as_unlimited(
    client, customer_auth, session, tenant, address, variant, add_to_cart, place_order
):
    await _make_coupon(session, tenant, code="ZEROPERCUST", per_customer_usage_limit=0)
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, address["id"], "ZEROPERCUST")
    assert response.status_code == 400
