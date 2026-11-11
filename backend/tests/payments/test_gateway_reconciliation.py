"""What Razorpay itself reports decides payment state: capture, currency, refunds, tenants."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update

from app.catalogue.models import InventoryItem
from app.orders.models import Order
from app.orders.service import OrderService
from app.payments.models import Payment
from tests.conftest import headers_for
from tests.helpers import run_concurrently
from tests.payments.conftest import (
    ADMIN_ORDERS,
    CUSTOMERS,
    GATEWAY_ORDER_ID,
    GATEWAY_PAYMENT_ID,
    ORDERS,
    VERIFY,
    paise,
    post_webhook,
    verification,
    webhook,
)


def refund_event(event: str, refund_id: str, amount: int, currency: str = "INR") -> bytes:
    entity = {
        "id": refund_id,
        "payment_id": GATEWAY_PAYMENT_ID,
        "amount": amount,
        "currency": currency,
    }
    return json.dumps({"event": event, "payload": {"refund": {"entity": entity}}}).encode()


async def _order(client, headers, order_id) -> dict:
    response = await client.get(f"{ORDERS}/{order_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _paid_and_cancelled(client, customer_auth, admin_headers, order_id) -> None:
    assert (await client.post(VERIFY, json=verification(), headers=customer_auth)).status_code == 200
    cancelled = await client.patch(
        f"{ADMIN_ORDERS}/{order_id}/status", json={"status": "CANCELLED"}, headers=admin_headers
    )
    assert cancelled.status_code == 200, cancelled.text


async def test_an_authorized_but_uncaptured_payment_is_not_paid_yet(
    client, customer_auth, online_order, gateway
):
    gateway.payment_status = "authorized"

    response = await client.post(VERIFY, json=verification(), headers=customer_auth)

    assert response.status_code == 400, response.text
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PENDING"

    captured = await post_webhook(client, webhook("payment.captured", paise(online_order)))

    assert captured.json()["data"]["result"] == "processed"
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PAID"


async def test_verify_rejects_a_payment_in_another_currency(
    client, customer_auth, online_order, gateway
):
    gateway.payment_currency = "USD"

    response = await client.post(VERIFY, json=verification(), headers=customer_auth)

    assert response.status_code == 400
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PENDING"


async def test_verify_rejects_a_payment_belonging_to_another_razorpay_order(
    client, customer_auth, online_order, gateway, monkeypatch
):
    async def elsewhere(payment_id):
        return {
            "id": payment_id,
            "order_id": "order_SOMEONE_ELSE",
            "status": "captured",
            "amount": paise(online_order),
            "currency": "INR",
        }

    monkeypatch.setattr("app.payments.razorpay.fetch_payment", elsewhere)

    response = await client.post(VERIFY, json=verification(), headers=customer_auth)

    assert response.status_code == 400


async def test_a_captured_webhook_in_another_currency_is_ignored(
    client, customer_auth, online_order
):
    body = webhook("payment.captured", paise(online_order), currency="USD")

    response = await post_webhook(client, body)

    assert response.json()["data"]["result"] == "ignored"
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PENDING"


async def test_a_refund_made_outside_the_app_is_still_recorded(
    client, customer_auth, admin_headers, online_order
):
    await _paid_and_cancelled(client, customer_auth, admin_headers, online_order["id"])

    response = await post_webhook(
        client, refund_event("refund.processed", "rfnd_DASHBOARD", paise(online_order))
    )

    assert response.json()["data"]["result"] == "processed"
    order = await _order(client, customer_auth, online_order["id"])
    assert order["payment_status"] == "REFUNDED"


async def test_a_partial_refund_is_not_recorded_as_a_full_one(
    client, customer_auth, admin_headers, online_order
):
    await _paid_and_cancelled(client, customer_auth, admin_headers, online_order["id"])

    response = await post_webhook(
        client, refund_event("refund.processed", "rfnd_PARTIAL", paise(online_order) // 2)
    )

    assert response.json()["data"]["result"] == "ignored"
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PAID"


async def test_a_failure_for_some_other_refund_leaves_ours_alone(
    client, session, customer_auth, admin_headers, online_order
):
    await _paid_and_cancelled(client, customer_auth, admin_headers, online_order["id"])
    await session.execute(
        update(Payment)
        .where(Payment.order_id == UUID(online_order["id"]))
        .values(razorpay_refund_id="rfnd_OURS")
    )
    await session.commit()

    await post_webhook(client, refund_event("refund.failed", "rfnd_OTHER", paise(online_order)))

    stored = await session.scalar(
        select(Payment.razorpay_refund_id)
        .where(Payment.order_id == UUID(online_order["id"]))
        .execution_options(populate_existing=True)
    )
    assert stored == "rfnd_OURS"


async def test_the_webhook_works_whatever_host_delivers_it(
    client, other_client, customer_auth, online_order
):
    response = await post_webhook(other_client, webhook("payment.captured", paise(online_order)))

    assert response.json()["data"]["result"] == "processed"
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PAID"


async def test_a_webhook_for_an_unknown_order_changes_nothing(client, customer_auth, online_order):
    body = webhook("payment.captured", paise(online_order), order_id="order_NOT_OURS")

    response = await post_webhook(client, body)

    assert response.json()["data"]["result"] == "ignored"
    assert (await _order(client, customer_auth, online_order["id"]))["payment_status"] == "PENDING"


async def test_another_tenants_customer_cannot_confirm_the_payment(
    other_client, make_user, other_tenant, online_order
):
    outsider = await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_b"])

    response = await other_client.post(
        VERIFY, json=verification(), headers=headers_for(outsider)
    )

    assert response.status_code == 404


async def test_an_order_nobody_tried_to_pay_expires(session, tenant, online_order, monkeypatch):
    async def no_attempts(_order_id):
        return []

    monkeypatch.setattr("app.payments.razorpay.fetch_order_payment_statuses", no_attempts)
    await session.execute(
        update(Order)
        .where(Order.id == UUID(online_order["id"]))
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=2))
    )
    await session.commit()

    assert await OrderService(session, tenant.id).expire_unpaid_online() == 1


async def test_two_expiry_workers_at_once_expire_an_order_once(
    engine, session, tenant, online_order, variant, monkeypatch
):
    async def all_failed(_order_id):
        return ["failed"]

    monkeypatch.setattr("app.payments.razorpay.fetch_order_payment_statuses", all_failed)
    await session.execute(
        update(Order)
        .where(Order.id == UUID(online_order["id"]))
        .values(created_at=datetime.now(timezone.utc) - timedelta(hours=2))
    )
    await session.commit()

    async def expire(db, _index):
        return await OrderService(db, tenant.id).expire_unpaid_online()

    results = await run_concurrently(engine, 2, expire)

    assert sorted(results) == [0, 1], results
    stock = await session.scalar(
        select(InventoryItem)
        .where(InventoryItem.variant_id == UUID(variant["id"]))
        .execution_options(populate_existing=True)
    )
    assert stock.reserved_quantity == 0
    assert stock.available_quantity == 10


async def test_the_gateway_order_is_what_checkout_created(online_order):
    assert online_order["payment"]["gateway_order_id"] == GATEWAY_ORDER_ID
