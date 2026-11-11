"""Fixtures for the payment tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal

import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.payments.razorpay import to_subunits
from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.conftest import headers_for
from tests.helpers import load_data, sample

DATA = load_data(__file__)

PAYMENTS = DATA["routes"]["payments"]
ADMIN_PAYMENTS = DATA["routes"]["admin_payments"]
ADMIN_ORDERS = DATA["routes"]["admin_orders"]
ADDRESSES = DATA["routes"]["addresses"]
CHECKOUT = DATA["routes"]["checkout"]
CART = DATA["routes"]["cart"]
ORDERS = DATA["routes"]["orders"]

CUSTOMERS = DATA["customers"]


@pytest_asyncio.fixture(loop_scope="session")
async def customer(make_user, tenant):
    return await make_user(tenant=tenant, phone=CUSTOMERS["payer"])


@pytest.fixture
def customer_auth(customer) -> dict[str, str]:
    return headers_for(customer)


@pytest_asyncio.fixture(loop_scope="session")
async def variant(client, admin_headers, tax_ready) -> dict:
    """An ACTIVE variant priced at 999.00 with 10 in stock."""
    category = await make_category(client, admin_headers, name="Payment Test Category")
    product = await make_product(
        client, admin_headers, category["id"], name="Kurta", status="ACTIVE"
    )

    payload = sample(DATA, "variant")
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants", json=payload, headers=admin_headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


@pytest_asyncio.fixture(loop_scope="session")
async def make_order(client):
    """Factory: `await make_order(headers, variant_id, quantity=2)` -> order."""

    async def _make(
        headers,
        variant_id,
        quantity: int = 2,
        payment_method: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict:
        added = await client.post(
            f"{CART}/items",
            json={"variant_id": variant_id, "quantity": quantity},
            headers=headers,
        )
        assert added.status_code == 201, added.text

        saved = await client.post(
            ADDRESSES, json=sample(DATA, "address"), headers=headers
        )
        assert saved.status_code == 201, saved.text

        payload = {"address_id": saved.json()["data"]["id"]}
        if payment_method is not None:
            payload["payment_method"] = payment_method
        request_headers = dict(headers)
        if idempotency_key is not None:
            request_headers["Idempotency-Key"] = idempotency_key
        placed = await client.post(CHECKOUT, json=payload, headers=request_headers)
        assert placed.status_code == 201, placed.text
        return placed.json()["data"]

    return _make


@pytest_asyncio.fixture(loop_scope="session")
async def order(make_order, customer_auth, variant) -> dict:
    """A placed order: 2 x 999.00 = 1998.00, PENDING and unpaid."""
    return await make_order(customer_auth, variant["id"], 2)


@pytest_asyncio.fixture(loop_scope="session")
async def payment(order) -> dict:
    """The COD payment checkout wrote for `order`: PENDING."""
    assert order["payment"] is not None, order
    return order["payment"]


KEY_SECRET = "test-key-secret"
WEBHOOK_SECRET = "test-webhook-secret"
GATEWAY_ORDER_ID = "order_TEST0001"
GATEWAY_PAYMENT_ID = "pay_TEST0001"

VERIFY = f"{PAYMENTS}/razorpay/verify"
WEBHOOK = f"{PAYMENTS}/razorpay/webhook"


def signature(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


def verification(order_id: str = GATEWAY_ORDER_ID, payment_id: str = GATEWAY_PAYMENT_ID):
    return {
        "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": signature(KEY_SECRET, f"{order_id}|{payment_id}".encode()),
    }


def webhook(
    event: str, amount: int, order_id: str = GATEWAY_ORDER_ID, currency: str = "INR"
) -> bytes:
    return json.dumps(
        {
            "event": event,
            "payload": {
                "payment": {
                    "entity": {
                        "id": GATEWAY_PAYMENT_ID,
                        "order_id": order_id,
                        "status": "captured",
                        "amount": amount,
                        "currency": currency,
                    }
                }
            },
        }
    ).encode()


def paise(order: dict) -> int:
    return to_subunits(Decimal(order["payment"]["amount"]))


async def post_webhook(client, body: bytes, secret: str = WEBHOOK_SECRET):
    return await client.post(
        WEBHOOK,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": signature(secret, body),
        },
    )


@pytest.fixture
def razorpay_keys(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)


class FakeGateway(list):
    """Orders Razorpay was asked to create, plus how it reports their payment."""

    payment_status = "captured"
    payment_currency = "INR"


@pytest.fixture
def gateway(monkeypatch, razorpay_keys):
    """Stands in for Razorpay's Orders and Payments APIs."""
    calls = FakeGateway()

    async def create_order(amount, currency, receipt) -> str:
        calls.append({"amount": amount, "currency": currency, "receipt": receipt})
        return GATEWAY_ORDER_ID

    async def fetch_payment(payment_id: str) -> dict:
        return {
            "id": payment_id,
            "order_id": GATEWAY_ORDER_ID,
            "status": calls.payment_status,
            "captured": calls.payment_status == "captured",
            "amount": to_subunits(calls[-1]["amount"]),
            "currency": calls.payment_currency,
        }

    monkeypatch.setattr("app.payments.razorpay.create_order", create_order)
    monkeypatch.setattr("app.payments.razorpay.fetch_payment", fetch_payment)
    return calls


async def checkout(client, headers, variant_id, body: dict):
    added = await client.post(
        f"{CART}/items", json={"variant_id": variant_id, "quantity": 2}, headers=headers
    )
    assert added.status_code == 201, added.text
    saved = await client.post(ADDRESSES, json=sample(DATA, "address"), headers=headers)
    assert saved.status_code == 201, saved.text
    return await client.post(
        CHECKOUT,
        json={"address_id": saved.json()["data"]["id"], **body},
        headers={**headers, "Idempotency-Key": "test-key"},
    )


@pytest_asyncio.fixture(loop_scope="session")
async def online_order(client, customer_auth, variant, gateway) -> dict:
    response = await checkout(
        client, customer_auth, variant["id"], {"coupon_code": None, "payment_method": "UPI"}
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]
