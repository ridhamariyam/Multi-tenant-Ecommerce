from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.coupons.models import Coupon, CouponUsage
from app.coupons.repository import CouponRepository, CouponUsageRepository
from app.coupons.service import CouponService
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.orders.service import CheckoutService
from app.payments.constants import PaymentStatus
from tests.conftest import headers_for
from tests.helpers import run_concurrently, succeeded


async def _make_coupon(session: AsyncSession, tenant, **overrides) -> Coupon:
    repo = CouponRepository(session, tenant.id)
    defaults = dict(
        tenant_id=tenant.id,
        code="TESTCODE",
        discount_type="FIXED_AMOUNT",
        discount_value=Decimal("50.00"),
        is_active=True,
    )
    defaults.update(overrides)
    coupon = Coupon(**defaults)
    await repo.add(coupon)
    await session.commit()
    return coupon


async def _make_order(session: AsyncSession, tenant, customer) -> Order:
    """A minimal, valid Order row -- CouponUsage.order_id is a real FK to
    orders.id, so record_usage()/CouponUsage tests need one to point at.
    Reading the Order model here isn't touching the Orders module."""
    order = Order(
        tenant_id=tenant.id,
        customer_id=customer.id,
        order_number=f"ORD-{uuid4().hex[:10].upper()}",
        status=OrderStatus.DELIVERED.value,
        payment_status=PaymentStatus.PAID.value,
        subtotal=Decimal("300.00"),
        shipping_amount=Decimal("0.00"),
        tax_amount=Decimal("0.00"),
        total_amount=Decimal("300.00"),
        delivery_name="Coupon Tester",
        delivery_phone="+919876500003",
        delivery_address_line_1="1 Test Street",
        delivery_city="Testville",
        delivery_state="TS",
        delivery_postal_code="100001",
        delivery_country="IN",
    )
    session.add(order)
    await session.commit()
    return order


@pytest.mark.asyncio
async def test_admin_create_coupon(client: AsyncClient, admin_headers: dict, tenant):
    response = await client.post(
        "/api/v1/admin/coupons",
        json={
            "code": "SAVE20",
            "discount_type": "PERCENTAGE",
            "discount_value": "20.00",
            "min_order_amount": "100.00",
            "max_discount_amount": "50.00",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["code"] == "SAVE20"
    assert data["discount_type"] == "PERCENTAGE"
    assert Decimal(data["discount_value"]) == Decimal("20.00")
    assert Decimal(data["min_order_amount"]) == Decimal("100.00")
    assert Decimal(data["max_discount_amount"]) == Decimal("50.00")
    assert data["is_active"] is True


@pytest.mark.asyncio
async def test_admin_create_fixed_coupon(client: AsyncClient, admin_headers: dict, tenant):
    response = await client.post(
        "/api/v1/admin/coupons",
        json={
            "code": "FLAT100",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": "100.00",
            "is_active": True,
        },
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["code"] == "FLAT100"
    assert data["discount_type"] == "FIXED_AMOUNT"
    assert Decimal(data["discount_value"]) == Decimal("100.00")


@pytest.mark.asyncio
async def test_admin_list_coupons(client: AsyncClient, staff_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(session, tenant, code="LISTME")

    response = await client.get("/api/v1/admin/coupons", headers=staff_headers)
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["meta"]["total_items"] >= 1
    codes = [item["code"] for item in res_data["data"]]
    assert "LISTME" in codes


@pytest.mark.asyncio
async def test_customer_apply_coupon_success(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(
        session, tenant, code="PROMO10", min_order_amount=Decimal("200.00")
    )

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "promo10"},
        headers=customer_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["code"] == "PROMO10"
    assert Decimal(data["discount_amount"]) == Decimal("50.00")


@pytest.mark.asyncio
async def test_customer_apply_coupon_min_order_fail(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(
        session, tenant, code="MINORDER", min_order_amount=Decimal("500.00")
    )

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "MINORDER"},
        headers=customer_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_customer_apply_expired_coupon(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    past_time = datetime.now(timezone.utc) - timedelta(days=2)
    await _make_coupon(session, tenant, code="EXPIRED", expires_at=past_time)

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "EXPIRED"},
        headers=customer_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_percentage_coupon_without_cap(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(
        session,
        tenant,
        code="TENPCT",
        discount_type="PERCENTAGE",
        discount_value=Decimal("10.00"),
    )

    await cart_worth(customer_headers, "200.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "TENPCT"},
        headers=customer_headers,
    )
    assert response.status_code == 200
    assert Decimal(response.json()["data"]["discount_amount"]) == Decimal("20.00")


@pytest.mark.asyncio
async def test_percentage_coupon_with_max_cap(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(
        session,
        tenant,
        code="BIGSALE",
        discount_type="PERCENTAGE",
        discount_value=Decimal("50.00"),  # 50% off
        max_discount_amount=Decimal("75.00"),  # Capped at 75
    )

    # Subtotal 300 -> 50% is 150, but cap is 75
    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "BIGSALE"},
        headers=customer_headers,
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert Decimal(data["discount_amount"]) == Decimal("75.00")


# ------------------------------ creation/update validation ------------------------------


@pytest.mark.asyncio
async def test_admin_create_duplicate_coupon_code_rejected(client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(session, tenant, code="DUPCODE")

    response = await client.post(
        "/api/v1/admin/coupons",
        json={"code": "dupcode", "discount_type": "FIXED_AMOUNT", "discount_value": "10.00"},
        headers=admin_headers,
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_admin_create_coupon_invalid_discount_value(client: AsyncClient, admin_headers: dict):
    response = await client.post(
        "/api/v1/admin/coupons",
        json={"code": "BADVAL", "discount_type": "FIXED_AMOUNT", "discount_value": "0.00"},
        headers=admin_headers,
    )
    assert response.status_code == 422

    response = await client.post(
        "/api/v1/admin/coupons",
        json={"code": "BADVAL2", "discount_type": "FIXED_AMOUNT", "discount_value": "-10.00"},
        headers=admin_headers,
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_create_coupon_invalid_percentage(client: AsyncClient, admin_headers: dict):
    response = await client.post(
        "/api/v1/admin/coupons",
        json={"code": "TOOBIG", "discount_type": "PERCENTAGE", "discount_value": "150.00"},
        headers=admin_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_create_coupon_invalid_dates(client: AsyncClient, admin_headers: dict):
    starts = datetime.now(timezone.utc) + timedelta(days=5)
    expires = datetime.now(timezone.utc) + timedelta(days=1)

    response = await client.post(
        "/api/v1/admin/coupons",
        json={
            "code": "BADDATES",
            "discount_type": "FIXED_AMOUNT",
            "discount_value": "10.00",
            "starts_at": starts.isoformat(),
            "expires_at": expires.isoformat(),
        },
        headers=admin_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_update_coupon_invalid_percentage_rejected(
    client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="UPDPCT", discount_type="PERCENTAGE", discount_value=Decimal("10.00"))

    response = await client.put(
        f"/api/v1/admin/coupons/{coupon.id}",
        json={"discount_value": "150.00"},
        headers=admin_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_update_coupon_invalid_dates_rejected(
    client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="UPDDATES")
    starts = datetime.now(timezone.utc) + timedelta(days=5)
    expires = datetime.now(timezone.utc) + timedelta(days=1)

    response = await client.put(
        f"/api/v1/admin/coupons/{coupon.id}",
        json={"starts_at": starts.isoformat(), "expires_at": expires.isoformat()},
        headers=admin_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_create_coupon_negative_limits_rejected(client: AsyncClient, admin_headers: dict):
    for field, value in [
        ("min_order_amount", "-1.00"),
        ("max_discount_amount", "-1.00"),
        ("usage_limit", -1),
        ("per_customer_usage_limit", -1),
    ]:
        response = await client.post(
            "/api/v1/admin/coupons",
            json={
                "code": f"NEG-{field}",
                "discount_type": "FIXED_AMOUNT",
                "discount_value": "10.00",
                field: value,
            },
            headers=admin_headers,
        )
        assert response.status_code == 422, f"{field} should reject negative values"


# ------------------------------ apply validation rules ------------------------------


@pytest.mark.asyncio
async def test_apply_coupon_not_found(cart_worth, client: AsyncClient, customer_headers: dict):
    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "DOESNOTEXIST"},
        headers=customer_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_apply_inactive_coupon_rejected(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(session, tenant, code="INACTIVE1", is_active=False)

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "INACTIVE1"},
        headers=customer_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_apply_not_yet_started_coupon_rejected(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    future_time = datetime.now(timezone.utc) + timedelta(days=2)
    await _make_coupon(session, tenant, code="NOTSTARTED", starts_at=future_time)

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "NOTSTARTED"},
        headers=customer_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_apply_coupon_global_usage_limit_reached(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    await _make_coupon(session, tenant, code="MAXEDOUT", usage_limit=1, times_used=1)

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "MAXEDOUT"},
        headers=customer_headers,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_apply_coupon_per_customer_usage_limit_reached(
    cart_worth, client: AsyncClient, session: AsyncSession, tenant, make_user
):
    customer = await make_user(tenant=tenant, phone="+919000222001")
    other_order = await _make_order(session, tenant, customer)
    coupon = await _make_coupon(session, tenant, code="ONEPERPERSON", per_customer_usage_limit=1)

    usage_repo = CouponUsageRepository(session, tenant.id)
    await usage_repo.add(
        CouponUsage(
            tenant_id=tenant.id,
            coupon_id=coupon.id,
            customer_id=customer.id,
            order_id=other_order.id,
            discount_amount=Decimal("10.00"),
            used_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()

    await cart_worth(headers_for(customer), "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "ONEPERPERSON"},
        headers=headers_for(customer),
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_apply_coupon_case_insensitive_code(cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant):
    await _make_coupon(session, tenant, code="MIXEDCASE")

    await cart_worth(customer_headers, "300.00")
    for code in ("mixedcase", "MixedCase", "MIXEDCASE"):
        response = await client.post(
            "/api/v1/coupons/apply",
            json={"code": code},
            headers=customer_headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["code"] == "MIXEDCASE"


@pytest.mark.asyncio
async def test_apply_coupon_ignores_a_client_supplied_subtotal(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    await _make_coupon(
        session, tenant, code="NEGSUB", discount_type="PERCENTAGE", discount_value=Decimal("10.00")
    )
    await cart_worth(customer_headers, "300.00")

    for forged in ("-1.00", "999999.00"):
        response = await client.post(
            "/api/v1/coupons/apply",
            json={"code": "NEGSUB"},
            params={"subtotal": forged},
            headers=customer_headers,
        )
        assert response.status_code == 200, response.text
        assert Decimal(response.json()["data"]["discount_amount"]) == Decimal("30.00")


@pytest.mark.asyncio
async def test_apply_coupon_needs_a_cart(
    client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    await _make_coupon(session, tenant, code="NOCART")

    response = await client.post(
        "/api/v1/coupons/apply", json={"code": "NOCART"}, headers=customer_headers
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_apply_coupon_discount_does_not_exceed_subtotal(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    await _make_coupon(session, tenant, code="OVERCAP", discount_value=Decimal("500.00"))

    await cart_worth(customer_headers, "50.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "OVERCAP"},
        headers=customer_headers,
    )
    assert response.status_code == 200
    assert Decimal(response.json()["data"]["discount_amount"]) == Decimal("50.00")


@pytest.mark.asyncio
async def test_apply_coupon_tenant_isolation(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant, other_tenant
):
    """A coupon created for one tenant must be invisible to another."""
    await _make_coupon(session, other_tenant, code="OTHERTENANT")

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "OTHERTENANT"},
        headers=customer_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_list_coupons_tenant_isolation(
    client: AsyncClient, staff_headers: dict, session: AsyncSession, tenant, other_tenant
):
    await _make_coupon(session, other_tenant, code="OTHERTENANTLIST")

    response = await client.get("/api/v1/admin/coupons", headers=staff_headers)
    assert response.status_code == 200
    codes = [item["code"] for item in response.json()["data"]]
    assert "OTHERTENANTLIST" not in codes


# ------------------------------ soft delete ------------------------------


@pytest.mark.asyncio
async def test_delete_coupon_deactivates_instead_of_deleting(
    client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="TODELETE")

    response = await client.delete(f"/api/v1/admin/coupons/{coupon.id}", headers=admin_headers)
    assert response.status_code == 200

    await session.refresh(coupon)
    assert coupon.is_active is False


@pytest.mark.asyncio
async def test_deleted_coupon_remains_in_database(
    client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="STAYSINDB")
    coupon_id = coupon.id

    response = await client.delete(f"/api/v1/admin/coupons/{coupon_id}", headers=admin_headers)
    assert response.status_code == 200

    row = await session.scalar(select(Coupon).where(Coupon.id == coupon_id))
    assert row is not None
    assert row.is_active is False


@pytest.mark.asyncio
async def test_deactivated_coupon_is_not_applicable(
    cart_worth, client: AsyncClient, admin_headers: dict, customer_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="NOWDEAD")

    delete_response = await client.delete(f"/api/v1/admin/coupons/{coupon.id}", headers=admin_headers)
    assert delete_response.status_code == 200

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "NOWDEAD"},
        headers=customer_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_coupon_usage_history_survives_coupon_deactivation(
    client: AsyncClient, admin_headers: dict, session: AsyncSession, tenant, make_user
):
    customer = await make_user(tenant=tenant, phone="+919000222002")
    order = await _make_order(session, tenant, customer)
    coupon = await _make_coupon(session, tenant, code="HISTORYKEPT")

    service = CouponService(session, tenant.id)
    usage = await service.record_usage(coupon.id, customer.id, order.id, Decimal("25.00"))

    delete_response = await client.delete(f"/api/v1/admin/coupons/{coupon.id}", headers=admin_headers)
    assert delete_response.status_code == 200

    row = await session.scalar(select(CouponUsage).where(CouponUsage.id == usage.id))
    assert row is not None
    assert row.discount_amount == Decimal("25.00")


# ------------------------------ apply must not consume usage ------------------------------


@pytest.mark.asyncio
async def test_apply_coupon_does_not_increment_times_used(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="NOCONSUME")

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "NOCONSUME"},
        headers=customer_headers,
    )
    assert response.status_code == 200

    await session.refresh(coupon)
    assert coupon.times_used == 0


@pytest.mark.asyncio
async def test_apply_coupon_does_not_create_coupon_usage(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="NOUSAGEROW")

    await cart_worth(customer_headers, "300.00")
    response = await client.post(
        "/api/v1/coupons/apply",
        json={"code": "NOUSAGEROW"},
        headers=customer_headers,
    )
    assert response.status_code == 200

    usages = (
        await session.scalars(select(CouponUsage).where(CouponUsage.coupon_id == coupon.id))
    ).all()
    assert usages == []


@pytest.mark.asyncio
async def test_apply_coupon_repeatedly_does_not_consume_usage_limit(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    coupon = await _make_coupon(session, tenant, code="REUSABLE", usage_limit=1)

    await cart_worth(customer_headers, "300.00")
    for _ in range(5):
        response = await client.post(
            "/api/v1/coupons/apply",
            json={"code": "REUSABLE"},
            headers=customer_headers,
        )
        assert response.status_code == 200, response.text

    await session.refresh(coupon)
    assert coupon.times_used == 0


# ------------------------------ record_usage() ------------------------------


@pytest.mark.asyncio
async def test_record_usage_increments_times_used_and_creates_coupon_usage(
    session: AsyncSession, tenant, make_user
):
    customer = await make_user(tenant=tenant, phone="+919000222003")
    order = await _make_order(session, tenant, customer)
    coupon = await _make_coupon(session, tenant, code="RECORDME")

    service = CouponService(session, tenant.id)
    usage = await service.record_usage(coupon.id, customer.id, order.id, Decimal("15.00"))

    await session.refresh(coupon)
    assert coupon.times_used == 1

    assert usage.coupon_id == coupon.id
    assert usage.customer_id == customer.id
    assert usage.order_id == order.id
    assert usage.discount_amount == Decimal("15.00")

    row = await session.scalar(select(CouponUsage).where(CouponUsage.id == usage.id))
    assert row is not None


ADDRESS = {
    "full_name": "Coupon Racer",
    "phone": "+919876500009",
    "address_line_1": "9 Race Street",
    "city": "Kochi",
    "state": "Kerala",
    "postal_code": "682001",
    "country": "India",
}


@pytest.mark.asyncio
async def test_concurrent_checkouts_cannot_exceed_the_usage_limit(
    cart_worth, client: AsyncClient, engine, session: AsyncSession, tenant, make_user
):
    coupon = await _make_coupon(session, tenant, code="ONLYONCE", usage_limit=1)
    shoppers = []
    for phone in ("+919000333001", "+919000333002"):
        customer = await make_user(tenant=tenant, phone=phone)
        headers = headers_for(customer)
        await cart_worth(headers, "300.00")
        saved = await client.post("/api/v1/addresses", json=ADDRESS, headers=headers)
        assert saved.status_code == 201, saved.text
        shoppers.append((customer, saved.json()["data"]["id"]))

    async def place(db, index):
        customer, address_id = shoppers[index]
        return await CheckoutService(db, tenant.id, customer.id).place_order(
            UUID(address_id), "ONLYONCE"
        )

    results = await run_concurrently(engine, 2, place)

    assert len(succeeded(results)) == 1, results
    await session.refresh(coupon)
    assert coupon.times_used == 1


@pytest.mark.asyncio
async def test_apply_and_preview_agree(
    cart_worth, client: AsyncClient, customer_headers: dict, session: AsyncSession, tenant
):
    await _make_coupon(
        session,
        tenant,
        code="SAMEANSWER",
        discount_type="PERCENTAGE",
        discount_value=Decimal("15.00"),
        max_discount_amount=Decimal("40.00"),
    )
    await cart_worth(customer_headers, "199.99")

    applied = await client.post(
        "/api/v1/coupons/apply", json={"code": "SAMEANSWER"}, headers=customer_headers
    )
    previewed = await client.post(
        "/api/v1/checkout/preview", params={"coupon_code": "SAMEANSWER"}, headers=customer_headers
    )

    assert applied.status_code == 200, applied.text
    assert previewed.status_code == 200, previewed.text
    assert applied.json()["data"]["discount_amount"] == previewed.json()["data"]["discount_amount"]
