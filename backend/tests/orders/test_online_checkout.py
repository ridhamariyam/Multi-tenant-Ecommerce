"""Razorpay checkout creation and retry behavior (gateway calls are mocked)."""

from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from app.payments import razorpay
from tests.orders.conftest import CHECKOUT, ORDERS


@pytest.fixture(autouse=True)
def razorpay_keys(monkeypatch):
    monkeypatch.setattr(get_settings(), "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(get_settings(), "razorpay_key_secret", "test-key-secret")


async def test_checkout_preview_accepts_online_payment_method(
    client, customer_auth, variant, add_to_cart, preview_checkout
):
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await preview_checkout(customer_auth, payment_method="UPI")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["payment_method"] == "UPI"


async def test_online_checkout_returns_gateway_order_and_stays_pending(
    client, customer_auth, address, variant, add_to_cart, place_order, monkeypatch
):
    await add_to_cart(customer_auth, variant["id"], 1)
    monkeypatch.setattr(razorpay, "create_order", _async_value("order_test_123"))
    response = await place_order(customer_auth, address["id"], payment_method="UPI")

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["payment_method"] == "UPI"
    assert body["payment_status"] == "PENDING"
    assert body["payment"]["status"] == "PENDING"
    assert body["payment"]["gateway_order_id"] == "order_test_123"
    assert body["payment"]["amount"] == body["total_amount"]
    assert body["payment"]["currency"] == "INR"


async def test_online_checkout_reuses_pending_order_and_gateway_order(
    client, customer_auth, address, variant, add_to_cart, monkeypatch
):
    await add_to_cart(customer_auth, variant["id"], 1)
    calls = []

    async def create(*args):
        calls.append(args)
        return "order_retry_123"

    monkeypatch.setattr(razorpay, "create_order", create)
    headers = {**customer_auth, "Idempotency-Key": uuid4().hex}
    payload = {"address_id": address["id"], "payment_method": "UPI"}
    first = await client.post(CHECKOUT, json=payload, headers=headers)
    second = await client.post(CHECKOUT, json=payload, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert second.json()["data"]["payment"]["gateway_order_id"] == "order_retry_123"
    assert len(calls) == 1


async def test_ambiguous_gateway_failure_blocks_retry_without_new_gateway_order(
    client, customer_auth, address, variant, add_to_cart, monkeypatch
):
    await add_to_cart(customer_auth, variant["id"], 1)
    gateway_orders = []

    async def create(*args):
        # The remote side created the order, but its response was lost.
        gateway_orders.append("order_created_response_lost")
        raise ServiceUnavailableError("gateway response lost")

    monkeypatch.setattr(razorpay, "create_order", create)
    headers = {**customer_auth, "Idempotency-Key": uuid4().hex}
    payload = {"address_id": address["id"], "payment_method": "UPI"}

    failed = await client.post(CHECKOUT, json=payload, headers=headers)
    before_retry = await client.get(ORDERS, headers=customer_auth)
    assert before_retry.status_code == 200, before_retry.text
    before_ids = [item["id"] for item in before_retry.json()["data"]]
    recovered = await client.post(CHECKOUT, json=payload, headers=headers)
    after_retry = await client.get(ORDERS, headers=customer_auth)

    assert failed.status_code == 503
    assert recovered.status_code == 409, recovered.text
    assert "reconcile" in recovered.json()["message"].lower()
    assert len(gateway_orders) == 1
    assert after_retry.status_code == 200, after_retry.text
    assert [item["id"] for item in after_retry.json()["data"]] == before_ids
    assert len(before_ids) == 1
    detail = await client.get(f"{ORDERS}/{before_ids[0]}", headers=customer_auth)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["payment"]["gateway_order_id"] is None


async def test_retry_reuses_saved_gateway_order_without_creating_another(
    client, customer_auth, address, variant, add_to_cart, monkeypatch
):
    await add_to_cart(customer_auth, variant["id"], 1)
    calls = []

    async def create(*args):
        calls.append(args)
        return "order_stored_once_123"

    monkeypatch.setattr(razorpay, "create_order", create)
    headers = {**customer_auth, "Idempotency-Key": uuid4().hex}
    payload = {"address_id": address["id"], "payment_method": "UPI"}
    first = await client.post(CHECKOUT, json=payload, headers=headers)
    second = await client.post(CHECKOUT, json=payload, headers=headers)

    assert first.status_code == second.status_code == 201
    assert first.json()["data"]["id"] == second.json()["data"]["id"]
    assert (
        first.json()["data"]["payment"]["gateway_order_id"]
        == second.json()["data"]["payment"]["gateway_order_id"]
        == "order_stored_once_123"
    )
    assert len(calls) == 1


async def test_cod_checkout_remains_pending_without_gateway_call(
    client, customer_auth, address, variant, add_to_cart, place_order, monkeypatch
):
    await add_to_cart(customer_auth, variant["id"], 1)

    async def unexpected(*args):
        raise AssertionError("COD must not call Razorpay")

    monkeypatch.setattr(razorpay, "create_order", unexpected)
    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["payment_method"] == "CASH_ON_DELIVERY"
    assert body["payment"]["provider"] == "COD"
    assert body["payment_status"] == "PENDING"


def _async_value(value):
    async def _return(*args):
        return value

    return _return
