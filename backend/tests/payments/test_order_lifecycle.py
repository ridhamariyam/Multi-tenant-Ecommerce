"""Order and payment state under concurrency, refunds, expiry and the cancel contract."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select, update

from app.catalogue.models import InventoryItem
from app.core.exceptions import ServiceUnavailableError
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.orders.service import OrderService
from app.payments.models import Payment
from app.payments.service import PaymentService, handle_razorpay_webhook
from tests.conftest import headers_for
from tests.helpers import run_concurrently, succeeded
from tests.payments.conftest import (
    ADMIN_ORDERS,
    CUSTOMERS,
    GATEWAY_PAYMENT_ID,
    ORDERS,
    VERIFY,
    WEBHOOK_SECRET,
    paise,
    post_webhook,
    signature,
    verification,
    webhook,
)

REFUND_ID = "rfnd_TEST0001"
FULL_REFUND = 199800


def refund_webhook(
    event: str, refund_id: str = REFUND_ID, amount: int = FULL_REFUND, currency: str = "INR"
) -> bytes:
    return json.dumps(
        {
            "event": event,
            "payload": {
                "refund": {
                    "entity": {
                        "id": refund_id,
                        "payment_id": GATEWAY_PAYMENT_ID,
                        "amount": amount,
                        "currency": currency,
                    }
                }
            },
        }
    ).encode()


@pytest.fixture
def refunds(monkeypatch):
    """Stands in for Razorpay's refunds API; set `.status` before calling."""

    class Refunds:
        status = "pending"
        calls: list[dict] = []

    async def create_refund(**kwargs):
        Refunds.calls.append(kwargs)
        return REFUND_ID, Refunds.status

    Refunds.calls = []
    monkeypatch.setattr("app.payments.razorpay.create_refund", create_refund)
    return Refunds


async def _stock(session, variant_id) -> InventoryItem:
    return await session.scalar(
        select(InventoryItem)
        .where(InventoryItem.variant_id == UUID(variant_id))
        .execution_options(populate_existing=True)
    )


async def _status(client, admin_headers, order_id, value):
    return await client.patch(
        f"{ADMIN_ORDERS}/{order_id}/status", json={"status": value}, headers=admin_headers
    )


async def _refund(client, headers, order_id):
    return await client.post(f"{ADMIN_ORDERS}/{order_id}/refund", headers=headers)


async def _pay(client, customer_auth):
    response = await client.post(VERIFY, json=verification(), headers=customer_auth)
    assert response.status_code == 200, response.text


async def _cancel(client, admin_headers, order_id):
    response = await _status(client, admin_headers, order_id, "CANCELLED")
    assert response.status_code == 200, response.text


async def test_cancelling_twice_at_once_releases_stock_once(
    engine, session, tenant, make_order, make_user, customer_auth, variant
):
    order = await make_order(customer_auth, variant["id"], 2)
    other = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])
    await make_order(headers_for(other), variant["id"], 2)

    async def cancel(db, _index):
        return await OrderService(db, tenant.id).update_status(
            UUID(order["id"]), OrderStatus.CANCELLED
        )

    results = await run_concurrently(engine, 2, cancel)

    assert len(succeeded(results)) == 2
    stock = await _stock(session, variant["id"])
    assert stock.reserved_quantity == 2
    assert stock.available_quantity == 10


async def test_shipping_twice_at_once_takes_stock_off_the_shelf_once(
    client, engine, session, tenant, admin_headers, make_order, customer_auth, variant
):
    order = await make_order(customer_auth, variant["id"], 2)
    for value in ("CONFIRMED", "PROCESSING"):
        assert (await _status(client, admin_headers, order["id"], value)).status_code == 200

    async def ship(db, _index):
        return await OrderService(db, tenant.id).update_status(
            UUID(order["id"]), OrderStatus.SHIPPED
        )

    results = await run_concurrently(engine, 2, ship)

    assert len(succeeded(results)) == 2
    stock = await _stock(session, variant["id"])
    assert stock.available_quantity == 8
    assert stock.reserved_quantity == 0


async def test_payment_racing_a_cancel_always_ends_paid_and_consistent(
    engine, session, tenant, customer, online_order, variant
):
    async def act(db, index):
        if index == 0:
            return await OrderService(db, tenant.id).update_status(
                UUID(online_order["id"]), OrderStatus.CANCELLED
            )
        return await PaymentService(db, tenant.id).verify_razorpay_payment(
            customer.id, **verification(), currency="INR"
        )

    results = await run_concurrently(engine, 2, act)

    assert len(succeeded(results)) == 2, results
    order = await session.scalar(
        select(Order)
        .where(Order.id == UUID(online_order["id"]))
        .execution_options(populate_existing=True)
    )
    assert order.status == OrderStatus.CANCELLED.value
    assert order.payment_status == "PAID"
    assert order.payment.status == "PAID"
    assert (await _stock(session, variant["id"])).reserved_quantity == 0


async def test_verify_racing_a_webhook_records_one_payment(
    engine, session, tenant, customer, online_order
):
    body = webhook("payment.captured", paise(online_order))

    async def act(db, index):
        if index == 0:
            return await PaymentService(db, tenant.id).verify_razorpay_payment(
                customer.id, **verification(), currency="INR"
            )
        return await handle_razorpay_webhook(db, body, signature(WEBHOOK_SECRET, body))

    results = await run_concurrently(engine, 2, act)

    assert len(succeeded(results)) == 2, results
    payments = (
        await session.scalars(
            select(Payment)
            .where(Payment.order_id == UUID(online_order["id"]))
            .execution_options(populate_existing=True)
        )
    ).all()
    assert [p.status for p in payments] == ["PAID"]


async def test_only_a_cancelled_order_can_be_refunded(
    client, customer_auth, admin_headers, online_order, refunds
):
    await _pay(client, customer_auth)

    response = await _refund(client, admin_headers, online_order["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "REFUND_NOT_ALLOWED"
    assert refunds.calls == []


async def test_a_cash_order_has_nothing_to_refund(
    client, admin_headers, order, refunds
):
    await _cancel(client, admin_headers, order["id"])

    response = await _refund(client, admin_headers, order["id"])

    assert response.status_code == 409
    assert refunds.calls == []


async def test_a_refund_is_requested_once_and_settled_by_webhook(
    client, customer_auth, admin_headers, online_order, refunds
):
    await _pay(client, customer_auth)
    await _cancel(client, admin_headers, online_order["id"])

    first = await _refund(client, admin_headers, online_order["id"])
    second = await _refund(client, admin_headers, online_order["id"])

    assert first.status_code == 200, first.text
    assert first.json()["data"]["payment_status"] == "PAID"
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "REFUND_ALREADY_REQUESTED"
    assert len(refunds.calls) == 1
    assert refunds.calls[0]["payment_id"] == "pay_TEST0001"
    assert str(refunds.calls[0]["amount"]) == online_order["total_amount"]

    for _ in range(2):
        settled = await post_webhook(client, refund_webhook("refund.processed"))
        assert settled.status_code == 200, settled.text

    order = (await client.get(f"{ORDERS}/{online_order['id']}", headers=customer_auth)).json()
    assert order["data"]["payment_status"] == "REFUNDED"
    assert order["data"]["payment"]["status"] == "REFUNDED"


async def test_an_instant_refund_is_recorded_straight_away(
    client, customer_auth, admin_headers, online_order, refunds
):
    refunds.status = "processed"
    await _pay(client, customer_auth)
    await _cancel(client, admin_headers, online_order["id"])

    response = await _refund(client, admin_headers, online_order["id"])

    assert response.status_code == 200, response.text
    assert response.json()["data"]["payment_status"] == "REFUNDED"


async def test_a_failed_refund_can_be_requested_again(
    client, customer_auth, admin_headers, online_order, refunds
):
    await _pay(client, customer_auth)
    await _cancel(client, admin_headers, online_order["id"])
    assert (await _refund(client, admin_headers, online_order["id"])).status_code == 200

    failed = await post_webhook(client, refund_webhook("refund.failed"))
    retried = await _refund(client, admin_headers, online_order["id"])

    assert failed.status_code == 200
    assert retried.status_code == 200, retried.text
    assert len(refunds.calls) == 2


async def test_a_refund_the_gateway_rejects_changes_nothing(
    client, customer_auth, admin_headers, online_order, monkeypatch
):
    async def unavailable(**_kwargs):
        raise ServiceUnavailableError("down")

    monkeypatch.setattr("app.payments.razorpay.create_refund", unavailable)
    await _pay(client, customer_auth)
    await _cancel(client, admin_headers, online_order["id"])

    response = await _refund(client, admin_headers, online_order["id"])

    assert response.status_code == 503
    order = (await client.get(f"{ORDERS}/{online_order['id']}", headers=customer_auth)).json()
    assert order["data"]["payment_status"] == "PAID"


async def test_only_an_admin_can_refund(client, customer_auth, staff_headers, online_order):
    assert (await _refund(client, customer_auth, online_order["id"])).status_code == 403
    assert (await _refund(client, staff_headers, online_order["id"])).status_code == 403


async def test_money_arriving_after_cancellation_can_be_refunded(
    client, customer_auth, admin_headers, online_order, refunds
):
    await _cancel(client, admin_headers, online_order["id"])

    await _pay(client, customer_auth)
    order = (await client.get(f"{ORDERS}/{online_order['id']}", headers=customer_auth)).json()
    assert order["data"]["status"] == "CANCELLED"
    assert order["data"]["payment_status"] == "PAID"

    response = await _refund(client, admin_headers, online_order["id"])
    assert response.status_code == 200, response.text


@pytest.fixture
def gateway_status(monkeypatch):
    """Answers Razorpay's order-payments lookup; set `.statuses`, or `.down = True`."""

    class Status:
        statuses: list[str] = ["failed"]
        down = False

    async def fetch_order_payment_statuses(_order_id):
        if Status.down:
            raise ServiceUnavailableError("down")
        return Status.statuses

    monkeypatch.setattr(
        "app.payments.razorpay.fetch_order_payment_statuses", fetch_order_payment_statuses
    )
    return Status


async def _age(session, order_id, minutes: int = 120) -> None:
    await session.execute(
        update(Order)
        .where(Order.id == UUID(order_id))
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=minutes))
    )
    await session.commit()


async def test_an_abandoned_online_order_expires_and_gives_stock_back(
    session, tenant, online_order, variant, gateway_status
):
    await _age(session, online_order["id"])

    first = await OrderService(session, tenant.id).expire_unpaid_online()
    second = await OrderService(session, tenant.id).expire_unpaid_online()

    assert (first, second) == (1, 0)
    order = await session.scalar(
        select(Order)
        .where(Order.id == UUID(online_order["id"]))
        .execution_options(populate_existing=True)
    )
    assert order.status == OrderStatus.CANCELLED.value
    assert order.payment.status == "FAILED"
    stock = await _stock(session, variant["id"])
    assert stock.reserved_quantity == 0
    assert stock.available_quantity == 10


@pytest.mark.parametrize(
    "scenario",
    ["captured", "authorized", "in_progress", "one_failed_one_pending", "gateway_down", "recent"],
)
async def test_an_order_is_not_expired_when_in_doubt(
    session, tenant, online_order, gateway_status, scenario
):
    gateway_status.statuses = {
        "captured": ["captured"],
        "authorized": ["authorized"],
        "in_progress": ["created"],
        "one_failed_one_pending": ["failed", "created"],
    }.get(scenario, ["failed"])
    gateway_status.down = scenario == "gateway_down"
    if scenario != "recent":
        await _age(session, online_order["id"])

    expired = await OrderService(session, tenant.id).expire_unpaid_online()

    assert expired == 0
    order = await session.scalar(
        select(Order)
        .where(Order.id == UUID(online_order["id"]))
        .execution_options(populate_existing=True)
    )
    assert order.status == OrderStatus.PENDING.value


async def test_cash_orders_never_expire(session, tenant, order, gateway_status):
    await _age(session, order["id"])

    assert await OrderService(session, tenant.id).expire_unpaid_online() == 0


async def test_can_cancel_follows_the_backend_rule(
    client, customer_auth, admin_headers, make_order, variant, online_order
):
    cash = await make_order(customer_auth, variant["id"], 1)
    assert cash["can_cancel"] is True

    await _status(client, admin_headers, cash["id"], "PROCESSING")
    processing = (await client.get(f"{ORDERS}/{cash['id']}", headers=customer_auth)).json()
    assert processing["data"]["can_cancel"] is False
    refused = await client.post(f"{ORDERS}/{cash['id']}/cancel", headers=customer_auth)
    assert refused.status_code == 409

    assert online_order["can_cancel"] is False
    online_refused = await client.post(
        f"{ORDERS}/{online_order['id']}/cancel", headers=customer_auth
    )
    assert online_refused.status_code == 409
