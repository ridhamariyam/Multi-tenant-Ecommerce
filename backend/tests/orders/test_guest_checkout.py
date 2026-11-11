"""Buying without an account: guest cart -> guest checkout -> order linked by phone."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.orders.models import Order
from app.payments.models import Payment
from app.users.models import User
from tests.conftest import headers_for, sign_in_customer
from tests.orders.conftest import CART, CHECKOUT, ORDERS, address_payload

GUEST_PHONE = "+919833330001"
CONTACT = {"name": "Asha Guest", "phone": "9833330001", "email": "asha@example.com"}


async def _guest_cart(client, variant_id, quantity=1) -> dict[str, str]:
    cart = (await client.post(f"{CART}/guest")).json()["data"]
    headers = {"X-Cart-Token": cart["guest_token"]}
    added = await client.post(
        f"{CART}/items", json={"variant_id": variant_id, "quantity": quantity}, headers=headers
    )
    assert added.status_code == 201, added.text
    return headers


async def _checkout(client, headers, **overrides):
    payload = {"contact": CONTACT, "address": address_payload(), **overrides}
    return await client.post(f"{CHECKOUT}/guest", json=payload, headers=headers)


async def test_a_guest_previews_with_just_a_pincode(client, variant):
    headers = await _guest_cart(client, variant["id"], 2)

    response = await client.post(
        f"{CHECKOUT}/guest/preview", json={"pincode": "682001"}, headers=headers
    )

    body = response.json()["data"]
    assert response.status_code == 200
    assert Decimal(body["subtotal"]) == Decimal("1998.00")
    assert body["delivery"]["serviceable"] is True
    assert body["cod"]["available"] is True


async def test_a_guest_places_an_order(client, session, tenant, variant):
    headers = await _guest_cart(client, variant["id"], 1)

    response = await _checkout(client, headers)

    order = response.json()["data"]
    assert response.status_code == 201, response.text
    assert order["is_guest"] is True
    assert order["payment_method"] == "CASH_ON_DELIVERY"
    assert order["contact_email"] == "asha@example.com"
    assert order["delivery_address"]["city"] == "Bengaluru"
    user = await session.scalar(select(User).where(User.phone == GUEST_PHONE))
    assert user is not None
    assert user.role == "CUSTOMER"
    assert user.is_verified is False
    assert user.name == "Asha Guest"
    payment = await session.scalar(
        select(Payment).where(Payment.order_id == UUID(order["id"]))
    )
    assert payment is not None
    assert payment.provider == "COD"


async def test_guest_online_checkout_is_rejected_before_order_or_gateway_creation(
    client, session, tenant, variant, monkeypatch
):
    async def unexpected_gateway_call(*args, **kwargs):
        raise AssertionError("guest checkout must not create a Razorpay order")

    monkeypatch.setattr(
        "app.orders.router.PaymentService.start_online_payment", unexpected_gateway_call
    )
    headers = await _guest_cart(client, variant["id"], 1)

    response = await _checkout(client, headers, payment_method="UPI")

    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "GUEST_ONLINE_PAYMENT_UNAVAILABLE"
    assert await session.scalar(select(Order.id).where(Order.tenant_id == tenant.id)) is None
    assert await session.scalar(select(User.id).where(User.phone == GUEST_PHONE)) is None


async def test_the_guest_cart_is_spent_after_ordering(client, variant):
    headers = await _guest_cart(client, variant["id"], 1)
    await _checkout(client, headers)

    again = await _checkout(client, headers)

    assert again.status_code == 404


async def test_signing_in_later_shows_the_guest_order(client, msg91, variant):
    headers = await _guest_cart(client, variant["id"], 1)
    order = (await _checkout(client, headers)).json()["data"]

    tokens = await sign_in_customer(client, msg91, GUEST_PHONE)
    mine = await client.get(
        ORDERS, headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )

    assert [o["id"] for o in mine.json()["data"]] == [order["id"]]


async def test_an_existing_customer_phone_gets_the_order(client, make_user, tenant, variant):
    existing = await make_user(tenant=tenant, phone=GUEST_PHONE, email="old@example.com")
    headers = await _guest_cart(client, variant["id"], 1)

    order = (await _checkout(client, headers)).json()["data"]

    mine = await client.get(ORDERS, headers=headers_for(existing))
    assert [o["id"] for o in mine.json()["data"]] == [order["id"]]


async def test_a_staff_phone_cannot_check_out_as_guest(client, make_user, tenant, variant):
    await make_user(tenant=tenant, phone=GUEST_PHONE, role="STAFF", email="s@zeen.com")
    headers = await _guest_cart(client, variant["id"], 1)

    response = await _checkout(client, headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PHONE_NOT_ALLOWED"


async def test_guest_checkout_needs_a_cart_token(client, tenant):
    response = await client.post(
        f"{CHECKOUT}/guest", json={"contact": CONTACT, "address": address_payload()}
    )

    assert response.status_code == 422


async def test_an_empty_guest_cart_cannot_check_out(client, tenant):
    cart = (await client.post(f"{CART}/guest")).json()["data"]

    response = await _checkout(client, {"X-Cart-Token": cart["guest_token"]})

    assert response.status_code == 409


async def test_guest_checkout_is_idempotent(client, variant):
    headers = await _guest_cart(client, variant["id"], 1)
    keyed = {**headers, "Idempotency-Key": "guest-retry-1"}

    first = await _checkout(client, keyed)
    second = await _checkout(client, keyed)

    assert first.status_code == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]


async def test_guest_contact_is_validated(client, variant):
    headers = await _guest_cart(client, variant["id"], 1)

    response = await _checkout(client, headers, contact={**CONTACT, "email": "nope"})

    assert response.status_code == 422


async def test_a_guest_order_can_be_tracked_publicly(client, variant):
    headers = await _guest_cart(client, variant["id"], 1)
    order = (await _checkout(client, headers)).json()["data"]

    response = await client.get(
        "/api/v1/storefront/orders/track",
        params={"order_number": order["order_number"], "phone": GUEST_PHONE},
    )

    assert response.status_code == 200
