"""Paying online through Razorpay: checkout contract, signature checks and webhooks."""

from __future__ import annotations

from decimal import Decimal

from app.core.config import get_settings
from app.core.exceptions import ServiceUnavailableError
from tests.conftest import headers_for
from tests.payments.conftest import (
    ADMIN_ORDERS,
    CART,
    CHECKOUT,
    CUSTOMERS,
    GATEWAY_ORDER_ID,
    GATEWAY_PAYMENT_ID,
    ORDERS,
    VERIFY,
    checkout,
    paise,
    post_webhook,
    verification,
    webhook,
)


async def _order(client, headers, order_id) -> dict:
    response = await client.get(f"{ORDERS}/{order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_the_storefront_cash_payload_places_an_order(client, customer_auth, variant):
    response = await checkout(
        client,
        customer_auth,
        variant["id"],
        {"coupon_code": None, "payment_method": "CASH_ON_DELIVERY"},
    )

    assert response.status_code == 201, response.text
    order = response.json()["data"]
    assert order["payment_method"] == "CASH_ON_DELIVERY"
    assert order["payment"]["provider"] == "COD"
    assert order["payment"]["gateway_order_id"] is None


async def test_an_omitted_method_still_means_cash(client, customer_auth, variant):
    response = await checkout(client, customer_auth, variant["id"], {})

    assert response.status_code == 201, response.text
    assert response.json()["data"]["payment_method"] == "CASH_ON_DELIVERY"


async def test_an_unknown_method_is_rejected(client, customer_auth, variant):
    response = await checkout(
        client, customer_auth, variant["id"], {"payment_method": "BITCOIN"}
    )

    assert response.status_code == 422


async def test_the_storefront_preview_payload_is_accepted(client, customer_auth, variant):
    added = await client.post(
        f"{CART}/items", json={"variant_id": variant["id"], "quantity": 1}, headers=customer_auth
    )
    assert added.status_code == 201, added.text

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"address_id": None, "payment_method": "UPI"},
        headers=customer_auth,
    )

    assert response.status_code == 200, response.text
    preview = response.json()["data"]
    assert preview["payment_method"] == "UPI"
    assert preview["total_amount"] == "999.00"


async def test_an_online_order_opens_a_razorpay_order_for_the_server_total(
    online_order, gateway
):
    payment = online_order["payment"]

    assert online_order["payment_method"] == "UPI"
    assert online_order["payment_status"] == "PENDING"
    assert payment["provider"] == "RAZORPAY"
    assert payment["status"] == "PENDING"
    assert payment["gateway_order_id"] == GATEWAY_ORDER_ID
    assert len(gateway) == 1
    assert gateway[0]["amount"] == Decimal(online_order["total_amount"])
    assert gateway[0]["receipt"] == online_order["order_number"]


async def test_online_checkout_without_keys_places_nothing(
    client, customer_auth, variant, monkeypatch
):
    monkeypatch.setattr(get_settings(), "razorpay_key_id", None)

    response = await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})

    assert response.status_code == 503
    listing = await client.get(ORDERS, headers=customer_auth)
    assert listing.json()["meta"]["total_items"] == 0


async def test_a_gateway_failure_keeps_the_order_awaiting_payment(
    client, customer_auth, variant, razorpay_keys, monkeypatch
):
    async def unavailable(*_args) -> str:
        raise ServiceUnavailableError("down")

    monkeypatch.setattr("app.payments.razorpay.create_order", unavailable)

    response = await checkout(client, customer_auth, variant["id"], {"payment_method": "UPI"})

    assert response.status_code == 503
    listing = await client.get(ORDERS, headers=customer_auth)
    assert listing.json()["meta"]["total_items"] == 1
    order = await _order(client, customer_auth, listing.json()["data"][0]["id"])
    assert order["payment_status"] == "PENDING"
    assert order["payment"]["gateway_order_id"] is None


async def test_a_signed_payment_marks_the_order_paid(client, customer_auth, online_order):
    response = await client.post(VERIFY, json=verification(), headers=customer_auth)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "PAID"
    assert response.json()["data"]["gateway_payment_id"] == GATEWAY_PAYMENT_ID

    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PAID"
    assert order["status"] == "PENDING"


async def test_a_forged_signature_changes_nothing(client, customer_auth, online_order):
    forged = {**verification(), "razorpay_signature": "0" * 64}

    response = await client.post(VERIFY, json=forged, headers=customer_auth)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PAYMENT_INVALID_SIGNATURE"
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PENDING"
    assert order["status"] == "PENDING"


async def test_a_signature_for_another_payment_id_is_rejected(
    client, customer_auth, online_order
):
    mismatched = {**verification(), "razorpay_payment_id": "pay_SOMEONE_ELSE"}

    response = await client.post(VERIFY, json=mismatched, headers=customer_auth)

    assert response.status_code == 400


async def test_verifying_twice_is_harmless(client, customer_auth, online_order):
    first = await client.post(VERIFY, json=verification(), headers=customer_auth)
    second = await client.post(VERIFY, json=verification(), headers=customer_auth)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["data"]["status"] == "PAID"


async def test_another_customer_cannot_confirm_the_payment(
    client, make_user, tenant, online_order
):
    intruder = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])

    response = await client.post(VERIFY, json=verification(), headers=headers_for(intruder))

    assert response.status_code == 404


async def test_a_captured_webhook_marks_the_order_paid(client, customer_auth, online_order):
    amount = paise(online_order)

    response = await post_webhook(client, webhook("payment.captured", amount))

    assert response.status_code == 200, response.text
    assert response.json()["data"]["result"] == "processed"
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PAID"


async def test_a_redelivered_webhook_is_applied_once(
    client, customer_auth, admin_headers, online_order
):
    amount = paise(online_order)
    body = webhook("payment.captured", amount)

    first = await post_webhook(client, body)
    second = await post_webhook(client, body)

    assert first.status_code == 200
    assert second.status_code == 200
    payments = await client.get(
        f"/api/v1/admin/payments?order_id={online_order['id']}&status=PAID",
        headers=admin_headers,
    )
    assert payments.json()["meta"]["total_items"] == 1


async def test_a_webhook_with_a_bad_signature_is_refused(client, customer_auth, online_order):
    amount = paise(online_order)

    response = await post_webhook(
        client, webhook("payment.captured", amount), secret="not-the-secret"
    )

    assert response.status_code == 401
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PENDING"


async def test_a_webhook_for_the_wrong_amount_is_ignored(client, customer_auth, online_order):
    response = await post_webhook(client, webhook("payment.captured", 100))

    assert response.status_code == 200
    assert response.json()["data"]["result"] == "ignored"
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PENDING"


async def test_a_failed_attempt_leaves_the_order_payable(client, customer_auth, online_order):
    amount = paise(online_order)

    response = await post_webhook(client, webhook("payment.failed", amount))

    assert response.status_code == 200
    assert response.json()["data"]["result"] == "acknowledged"
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "PENDING"
    assert order["payment"]["status"] == "PENDING"


async def test_webhooks_are_refused_without_a_secret(client, online_order, monkeypatch):
    monkeypatch.setattr(get_settings(), "razorpay_webhook_secret", None)
    amount = paise(online_order)

    response = await post_webhook(client, webhook("payment.captured", amount))

    assert response.status_code == 503


async def test_a_paid_online_order_moves_on_and_delivery_keeps_it_paid(
    client, customer_auth, admin_headers, online_order
):
    paid = await client.post(VERIFY, json=verification(), headers=customer_auth)
    assert paid.status_code == 200, paid.text

    for value in ("PROCESSING", "SHIPPED", "DELIVERED"):
        response = await client.patch(
            f"{ADMIN_ORDERS}/{online_order['id']}/status",
            json={"status": value},
            headers=admin_headers,
        )
        assert response.status_code == 200, response.text

    order = response.json()["data"]
    assert order["payment_status"] == "PAID"
    assert order["payment"]["provider"] == "RAZORPAY"


async def test_a_customer_cannot_cancel_a_paid_online_order(
    client, customer_auth, online_order
):
    paid = await client.post(VERIFY, json=verification(), headers=customer_auth)
    assert paid.status_code == 200, paid.text

    response = await client.post(f"{ORDERS}/{online_order['id']}/cancel", headers=customer_auth)

    assert response.status_code == 409


async def test_an_unpaid_online_order_is_cancelled_by_the_store_not_the_customer(
    client, customer_auth, admin_headers, online_order
):
    refused = await client.post(f"{ORDERS}/{online_order['id']}/cancel", headers=customer_auth)
    assert refused.status_code == 409

    response = await client.patch(
        f"{ADMIN_ORDERS}/{online_order['id']}/status",
        json={"status": "CANCELLED"},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    order = response.json()["data"]
    assert order["status"] == "CANCELLED"
    assert order["payment"]["status"] == "FAILED"
