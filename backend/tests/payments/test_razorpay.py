"""Server-side Razorpay verification with gateway responses mocked."""

import asyncio
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import get_db
from app.main import app
from app.orders.models import Order
from app.orders.repository import OrderRepository
from app.payments import razorpay
from tests.conftest import headers_for
from tests.payments.conftest import ADMIN_ORDERS, CUSTOMERS, ORDERS, PAYMENTS


def _gateway_payment(order: dict, payment_id: str = "pay_verified_123") -> dict:
    return {
        "id": payment_id,
        "order_id": order["payment"]["gateway_order_id"],
        "amount": int(Decimal(order["payment"]["amount"]) * 100),
        "currency": order["payment"]["currency"],
        "status": "captured",
        "captured": True,
    }


def _verification(order: dict, payment_id: str = "pay_verified_123") -> dict:
    return {
        "razorpay_order_id": order["payment"]["gateway_order_id"],
        "razorpay_payment_id": payment_id,
        "razorpay_signature": "signature",
    }


async def _online_order(customer_auth, variant, make_order, monkeypatch):
    monkeypatch.setattr(razorpay.get_settings(), "razorpay_key_id", "rzp_test_key")
    monkeypatch.setattr(razorpay.get_settings(), "razorpay_key_secret", "test-key-secret")
    monkeypatch.setattr(razorpay, "create_order", _create_order)
    return await make_order(customer_auth, variant["id"], payment_method="UPI")


async def _create_order(*args):
    return "order_checkout_123"


async def test_successful_verification_and_repeat_are_idempotent(
    client, customer_auth, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    details = _gateway_payment(order)
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(razorpay, "fetch_payment", _async_payload(details))
    payload = _verification(order)

    first = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=payload, headers=customer_auth
    )
    second = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=payload, headers=customer_auth
    )

    assert first.status_code == second.status_code == 200
    assert first.json()["data"]["status"] == "PAID"
    assert first.json()["data"]["gateway_payment_id"] == "pay_verified_123"
    assert second.json()["data"]["gateway_payment_id"] == "pay_verified_123"


async def test_invalid_signature_is_rejected_before_gateway_lookup(
    client, customer_auth, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: False)

    response = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=_verification(order), headers=customer_auth
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    "change",
    [
        {"id": "pay_different_123"},
        {"order_id": "order_other_123"},
        {"amount": 1},
        {"currency": "USD"},
        {"status": "authorized", "captured": False},
    ],
    ids=["payment-id", "order-id", "amount", "currency", "uncaptured"],
)
async def test_mismatched_or_uncaptured_gateway_payment_is_rejected(
    client, customer_auth, variant, make_order, monkeypatch, change
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    details = _gateway_payment(order)
    details.update(change)
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(razorpay, "fetch_payment", _async_payload(details))

    response = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=_verification(order), headers=customer_auth
    )

    assert response.status_code == 400


async def test_payment_verification_is_scoped_to_order_owner(
    client, make_user, tenant, variant, make_order, customer_auth, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    other_customer = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(razorpay, "fetch_payment", _async_payload(_gateway_payment(order)))

    response = await client.post(
        f"{PAYMENTS}/razorpay/verify",
        json=_verification(order),
        headers=headers_for(other_customer),
    )

    assert response.status_code == 404


async def test_payment_verification_is_scoped_to_tenant(
    client, other_tenant, make_user, variant, make_order, customer_auth, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    other_customer = await make_user(
        tenant=other_tenant, phone=CUSTOMERS["tenant_b"]
    )
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(razorpay, "fetch_payment", _async_payload(_gateway_payment(order)))

    response = await client.post(
        f"{PAYMENTS}/razorpay/verify",
        json=_verification(order),
        headers=headers_for(other_customer),
    )

    # Another tenant's token is refused outright, before any order lookup.
    assert response.status_code == 401


async def test_different_payment_id_cannot_replace_a_paid_payment(
    client, customer_auth, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(razorpay, "fetch_payment", _async_payload(_gateway_payment(order)))
    first = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=_verification(order), headers=customer_auth
    )
    assert first.status_code == 200

    conflicting = _verification(order, payment_id="pay_conflict_456")
    response = await client.post(
        f"{PAYMENTS}/razorpay/verify", json=conflicting, headers=customer_auth
    )

    assert response.status_code == 409


async def test_paid_razorpay_order_cannot_be_cancelled(
    client, customer_auth, admin_headers, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(
        razorpay, "fetch_payment", _async_payload(_gateway_payment(order))
    )
    verified = await client.post(
        f"{PAYMENTS}/razorpay/verify",
        json=_verification(order),
        headers=customer_auth,
    )
    assert verified.status_code == 200, verified.text

    cancelled = await client.post(
        f"{ORDERS}/{order['id']}/cancel", headers=customer_auth
    )

    assert cancelled.status_code == 409
    read = await client.get(f"{ADMIN_ORDERS}/{order['id']}", headers=admin_headers)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["status"] == "PENDING"
    assert read.json()["data"]["payment_status"] == "PAID"
    assert read.json()["data"]["payment"]["status"] == "PAID"


async def test_cancellation_is_rejected_when_gateway_captured_before_verification(
    client, customer_auth, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    # Razorpay has captured the payment, but verification has not yet acquired
    # the order lock. Make cancellation acquire that lock first.
    cancellation_lock_held = asyncio.Event()
    allow_cancellation = asyncio.Event()
    verification_lock_attempted = asyncio.Event()
    lock_calls = 0
    original_lock = OrderRepository.get_for_customer_for_update

    async def observed_order_lock(repository, customer_id, order_id):
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 1:
            locked = await original_lock(repository, customer_id, order_id)
            cancellation_lock_held.set()
            await allow_cancellation.wait()
            return locked
        verification_lock_attempted.set()
        return await original_lock(repository, customer_id, order_id)

    monkeypatch.setattr(
        OrderRepository, "get_for_customer_for_update", observed_order_lock
    )
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    monkeypatch.setattr(
        razorpay, "fetch_payment", _async_payload(_gateway_payment(order))
    )

    cancelling = asyncio.create_task(
        client.post(f"{ORDERS}/{order['id']}/cancel", headers=customer_auth)
    )
    await asyncio.wait_for(cancellation_lock_held.wait(), timeout=5)
    verifying = asyncio.create_task(
        client.post(
            f"{PAYMENTS}/razorpay/verify",
            json=_verification(order),
            headers=customer_auth,
        )
    )
    await asyncio.wait_for(verification_lock_attempted.wait(), timeout=5)
    allow_cancellation.set()
    cancelled, verified = await asyncio.gather(cancelling, verifying)

    assert cancelled.status_code == 409, cancelled.text
    assert verified.status_code == 200, verified.text
    current = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)
    assert current.status_code == 200, current.text
    assert current.json()["data"]["status"] == "PENDING"
    assert current.json()["data"]["payment_status"] == "PAID"
    assert current.json()["data"]["payment"]["status"] == "PAID"


async def test_cancellation_waits_for_in_flight_payment_verification(
    client, engine, customer_auth, variant, make_order, monkeypatch
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    # The two requests must race on their own connections, as they would in
    # the app; the shared test session cannot run two statements at once.
    factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

    async def own_session():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = own_session
    monkeypatch.setattr(razorpay, "signature_is_valid", lambda *args: True)
    verification_in_gateway = asyncio.Event()
    release_gateway = asyncio.Event()
    cancellation_lock_attempted = asyncio.Event()
    lock_calls = 0
    original_lock = OrderRepository.get_for_customer_for_update

    async def delayed_fetch(*args):
        verification_in_gateway.set()
        await release_gateway.wait()
        return _gateway_payment(order)

    async def observed_order_lock(repository, customer_id, order_id):
        nonlocal lock_calls
        lock_calls += 1
        if lock_calls == 2:
            cancellation_lock_attempted.set()
        return await original_lock(repository, customer_id, order_id)

    monkeypatch.setattr(razorpay, "fetch_payment", delayed_fetch)
    monkeypatch.setattr(
        OrderRepository, "get_for_customer_for_update", observed_order_lock
    )

    verifying = asyncio.create_task(
        client.post(
            f"{PAYMENTS}/razorpay/verify",
            json=_verification(order),
            headers=customer_auth,
        )
    )
    await asyncio.wait_for(verification_in_gateway.wait(), timeout=5)
    cancelling = asyncio.create_task(
        client.post(f"{ORDERS}/{order['id']}/cancel", headers=customer_auth)
    )
    await asyncio.wait_for(cancellation_lock_attempted.wait(), timeout=5)
    release_gateway.set()
    verified, cancelled = await asyncio.gather(verifying, cancelling)

    assert verified.status_code == 200, verified.text
    assert cancelled.status_code == 409, cancelled.text
    read = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["status"] == "PENDING"
    assert read.json()["data"]["payment_status"] == "PAID"


async def test_unpaid_razorpay_order_cannot_ship_or_deliver(
    client, customer_auth, admin_headers, variant, make_order, monkeypatch, session
):
    order = await _online_order(customer_auth, variant, make_order, monkeypatch)
    for status in ("CONFIRMED", "PROCESSING"):
        moved = await client.patch(
            f"{ADMIN_ORDERS}/{order['id']}/status",
            json={"status": status},
            headers=admin_headers,
        )
        assert moved.status_code == 200, moved.text

    shipped = await client.patch(
        f"{ADMIN_ORDERS}/{order['id']}/status",
        json={"status": "SHIPPED"},
        headers=admin_headers,
    )
    assert shipped.status_code == 409
    after_shipping_attempt = await client.get(
        f"{ADMIN_ORDERS}/{order['id']}", headers=admin_headers
    )
    assert after_shipping_attempt.status_code == 200, after_shipping_attempt.text
    assert after_shipping_attempt.json()["data"]["status"] == "PROCESSING"

    # Exercise the delivery guard independently for an order already marked
    # shipped in persisted data (for example, a pre-existing invalid state).
    row = await session.get(Order, UUID(order["id"]))
    row.status = "SHIPPED"
    await session.commit()
    delivered = await client.patch(
        f"{ADMIN_ORDERS}/{order['id']}/status",
        json={"status": "DELIVERED"},
        headers=admin_headers,
    )

    assert delivered.status_code == 409
    read = await client.get(f"{ADMIN_ORDERS}/{order['id']}", headers=admin_headers)
    assert read.status_code == 200, read.text
    assert read.json()["data"]["status"] == "SHIPPED"
    assert read.json()["data"]["payment_status"] == "PENDING"
    assert read.json()["data"]["payment"]["status"] == "PENDING"


def _async_payload(value: dict):
    async def _return(*args):
        return value

    return _return
