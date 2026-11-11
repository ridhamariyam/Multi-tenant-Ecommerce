"""Each brand's own Razorpay account, and guests paying online."""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.payments import gateway as gateway_module
from app.payments import razorpay
from app.payments.gateway import PaymentGatewayAccount
from tests.orders.conftest import address_payload
from tests.payments.conftest import (
    CART,
    CHECKOUT,
    GATEWAY_ORDER_ID,
    GATEWAY_PAYMENT_ID,
    KEY_SECRET,
    PAYMENTS,
    WEBHOOK,
    checkout,
    paise,
    signature,
    verification,
    webhook,
)

SETTINGS = "/api/v1/admin/payment-gateway"
BRAND_KEY = "rzp_live_BrandOwn1234"
BRAND_SECRET = "brand-key-secret-value"
BRAND_WEBHOOK_SECRET = "brand-webhook-secret"


@pytest.fixture
def own_brand(monkeypatch, gateway):
    """The test store is NOT the platform's own: it must bring its own account."""
    monkeypatch.setattr(get_settings(), "razorpay_platform_tenant_slugs", ["the-operator"])
    checked: list[tuple[str, str]] = []

    async def check_keys(key_id, key_secret):
        checked.append((key_id, key_secret))

    monkeypatch.setattr(gateway_module, "check_keys", check_keys)
    return checked


async def _connect(client, admin_headers, **body):
    payload = {"key_id": BRAND_KEY, "key_secret": BRAND_SECRET, "webhook_secret": BRAND_WEBHOOK_SECRET, **body}
    return await client.put(SETTINGS, json=payload, headers=admin_headers)


async def test_a_brand_without_its_own_account_cannot_take_online_payment(
    client, own_brand, customer_auth, variant
):
    response = await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PAYMENT_GATEWAY_UNAVAILABLE"


async def test_connecting_stores_the_secret_encrypted_and_never_returns_it(
    client, session, own_brand, admin_headers
):
    response = await _connect(client, admin_headers)

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["source"] == "own" and data["connected"] is True and data["mode"] == "live"
    assert data["key_id"] == BRAND_KEY and data["has_webhook_secret"] is True
    assert data["webhook_url"].endswith(f"/payments/razorpay/webhook/{(await _tenant_id(session))}")
    assert BRAND_SECRET not in response.text and BRAND_WEBHOOK_SECRET not in response.text
    assert own_brand == [(BRAND_KEY, BRAND_SECRET)]  # checked with Razorpay first

    row = await session.scalar(select(PaymentGatewayAccount))
    assert BRAND_SECRET not in row.key_secret_encrypted
    assert BRAND_WEBHOOK_SECRET not in (row.webhook_secret_encrypted or "")
    assert await gateway_module.public_key_id(session, await _tenant_id(session)) == BRAND_KEY


async def _tenant_id(session):
    from app.tenants.models import Tenant

    return await session.scalar(select(Tenant.id).where(Tenant.slug == "zeen"))


async def test_a_wrong_key_id_or_missing_secret_is_refused(client, own_brand, admin_headers):
    bad = await _connect(client, admin_headers, key_id="not-a-key")
    missing = await _connect(client, admin_headers, key_secret=None)

    assert bad.status_code == 400
    assert missing.status_code == 400
    assert missing.json()["error"]["details"][0]["field"] == "key_secret"


async def test_staff_cannot_change_the_payment_account(client, own_brand, staff_headers):
    response = await _connect(client, staff_headers)
    assert response.status_code == 403


async def test_the_brands_own_keys_are_used_for_its_payments(
    client, monkeypatch, own_brand, admin_headers, customer_auth, variant, gateway
):
    await _connect(client, admin_headers)
    used: list[str] = []
    fake_create = razorpay.create_order

    async def create_order(amount, currency, receipt):
        used.append(razorpay.credentials().key_id)
        return await fake_create(amount, currency, receipt)

    monkeypatch.setattr("app.payments.razorpay.create_order", create_order)

    response = await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})

    assert response.status_code == 201, response.text
    assert used == [BRAND_KEY]
    # The browser's signature is made with the brand's secret, not the platform's.
    order_id, payment_id = GATEWAY_ORDER_ID, GATEWAY_PAYMENT_ID
    brand_signed = {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature(BRAND_SECRET, f"{order_id}|{payment_id}".encode()),
    }
    platform_signed = await client.post(f"{PAYMENTS}/razorpay/verify", json=verification(), headers=customer_auth)
    verified = await client.post(f"{PAYMENTS}/razorpay/verify", json=brand_signed, headers=customer_auth)
    assert platform_signed.status_code == 400
    assert verified.status_code == 200, verified.text
    assert verified.json()["data"]["status"] == "PAID"


async def test_webhooks_from_the_brands_account_use_its_secret(
    client, session, own_brand, admin_headers, customer_auth, variant
):
    await _connect(client, admin_headers)
    order = (await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})).json()["data"]
    body = webhook("payment.captured", paise(order))
    tenant_id = await _tenant_id(session)

    platform = await client.post(
        WEBHOOK, content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature("test-webhook-secret", body)},
    )
    wrong = await client.post(
        f"{WEBHOOK}/{tenant_id}", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature("test-webhook-secret", body)},
    )
    right = await client.post(
        f"{WEBHOOK}/{tenant_id}", content=body,
        headers={"Content-Type": "application/json", "X-Razorpay-Signature": signature(BRAND_WEBHOOK_SECRET, body)},
    )

    assert platform.json()["data"]["result"] == "ignored"  # platform account can't speak for the brand
    assert wrong.status_code == 401
    assert right.status_code == 200, right.text
    paid = (await client.get(f"/api/v1/orders/{order['id']}", headers=customer_auth)).json()["data"]
    assert paid["payment_status"] == "PAID"


async def test_disconnecting_turns_online_payment_off(client, session, own_brand, admin_headers):
    await _connect(client, admin_headers)

    response = await client.delete(SETTINGS, headers=admin_headers)

    assert response.json()["data"]["source"] == "none"
    assert await gateway_module.public_key_id(session, await _tenant_id(session)) is None


# ------------------------------------------------------------------ guests


async def _guest_online_order(client, variant_id) -> dict:
    cart = (await client.post(f"{CART}/guest")).json()["data"]
    headers = {"X-Cart-Token": cart["guest_token"]}
    added = await client.post(f"{CART}/items", json={"variant_id": variant_id, "quantity": 2}, headers=headers)
    assert added.status_code == 201, added.text
    response = await client.post(
        f"{CHECKOUT}/guest",
        json={
            "contact": {"name": "Asha Guest", "phone": "9833330001", "email": "asha@example.com"},
            "address": address_payload(),
            "payment_method": "UPI",
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_a_guest_pays_online_and_the_signature_confirms_it(client, variant, gateway):
    order = await _guest_online_order(client, variant["id"])

    assert order["is_guest"] is True and order["payment_method"] == "UPI"
    assert order["payment"]["gateway_order_id"] == GATEWAY_ORDER_ID
    forged = {**verification(), "razorpay_signature": "0" * 64}
    rejected = await client.post(f"{PAYMENTS}/razorpay/verify-guest", json=forged)
    verified = await client.post(f"{PAYMENTS}/razorpay/verify-guest", json=verification())

    assert rejected.status_code == 400
    assert verified.status_code == 200, verified.text
    assert verified.json()["data"]["status"] == "PAID"
    tracked = await client.get(
        "/api/v1/storefront/orders/track", params={"order_number": order["order_number"], "phone": "9833330001"}
    )
    assert tracked.status_code == 200


async def test_the_guest_route_cannot_confirm_a_signed_in_shoppers_order(client, customer_auth, variant, gateway):
    placed = await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})
    assert placed.status_code == 201

    response = await client.post(f"{PAYMENTS}/razorpay/verify-guest", json=verification())

    assert response.status_code == 404
    assert json.loads(response.text)["error"]["code"] == "PAYMENT_NOT_FOUND"
