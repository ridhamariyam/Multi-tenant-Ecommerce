"""Paying for an order, in cash, when it arrives."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.catalogue.service import InventoryService
from app.payments.repository import PaymentRepository
from tests.conftest import headers_for
from tests.payments.conftest import (
    ADMIN_ORDERS,
    ADMIN_PAYMENTS,
    CUSTOMERS,
    ORDERS,
    PAYMENTS,
)


async def _set_status(client, admin_headers, order_id, value):
    return await client.patch(
        f"{ADMIN_ORDERS}/{order_id}/status", json={"status": value}, headers=admin_headers
    )


async def _deliver(client, admin_headers, order_id):
    """Walk an order all the way to delivered, which is when the cash lands."""
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"):
        response = await _set_status(client, admin_headers, order_id, value)
        assert response.status_code == 200, response.text
    return response


async def _order(client, admin_headers, order_id) -> dict:
    response = await client.get(f"{ADMIN_ORDERS}/{order_id}", headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _payment(client, headers, payment_id) -> dict:
    response = await client.get(f"{PAYMENTS}/{payment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_checkout_creates_the_payment(client, admin_headers, order):
    response = await client.get(
        ADMIN_PAYMENTS, params={"order_id": order["id"]}, headers=admin_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["total_items"] == 1


async def test_the_order_carries_its_payment(client, customer_auth, order):
    """A customer never needs a second call, or a payment id from anywhere."""
    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)

    assert response.status_code == 200, response.text
    body = response.json()["data"]["payment"]
    assert body["order_id"] == order["id"]
    assert body["status"] == "PENDING"
    assert body["provider"] == "COD"
    assert body["currency"] == "INR"


async def test_the_payment_id_from_an_order_reaches_the_payment_endpoint(
    client, customer_auth, order
):
    """The id the order hands over is the one GET /payments/{id} accepts."""
    read = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)
    payment_id = read.json()["data"]["payment"]["id"]

    response = await client.get(f"{PAYMENTS}/{payment_id}", headers=customer_auth)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == payment_id


async def test_a_new_payment_is_cash_on_delivery_and_pending(client, customer_auth, payment):
    body = await _payment(client, customer_auth, payment["id"])

    assert body["status"] == "PENDING"
    assert body["provider"] == "COD"


async def test_the_amount_comes_from_the_order(order, payment):
    assert Decimal(payment["amount"]) == Decimal(order["total_amount"])
    assert Decimal(payment["amount"]) == Decimal("1998.00")


async def test_there_is_no_endpoint_that_creates_a_payment(client, customer_auth, order):
    """Nothing to choose with COD, so the route does not exist at all."""
    response = await client.post(
        PAYMENTS, json={"order_id": order["id"]}, headers=customer_auth
    )

    assert response.status_code == 404


async def test_an_order_never_exists_without_its_payment(
    client, admin_headers, customer_auth, variant, make_order
):
    second = await make_order(customer_auth, variant["id"], 1)

    response = await client.get(
        ADMIN_PAYMENTS, params={"order_id": second["id"]}, headers=admin_headers
    )
    assert response.json()["meta"]["total_items"] == 1
    assert Decimal(response.json()["data"][0]["amount"]) == Decimal("999.00")


async def test_the_currency_comes_from_the_tenant(client, customer_auth, payment):
    """Zeen sells in India, so its storefront prices in rupees."""
    assert (await _payment(client, customer_auth, payment["id"]))["currency"] == "INR"


async def test_an_order_reports_the_tenants_currency(client, customer_auth, order):
    read = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)
    listed = await client.get(ORDERS, headers=customer_auth)

    assert read.json()["data"]["currency"] == "INR"
    assert listed.json()["data"][0]["currency"] == "INR"


async def test_a_tenant_carries_its_own_currency(session, tenant, other_tenant):
    """The column is per tenant, so a second storefront can price elsewhere."""
    assert tenant.currency == "INR"

    other_tenant.currency = "AED"
    await session.commit()

    assert other_tenant.currency == "AED"


async def test_a_currency_must_be_an_iso_code(session, other_tenant):
    """The check constraint holds it to three upper-case letters."""
    other_tenant.currency = "inr"

    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_delivering_the_order_collects_the_cash(
    client, admin_headers, customer_auth, order, payment
):
    await _deliver(client, admin_headers, order["id"])

    assert (await _payment(client, customer_auth, payment["id"]))["status"] == "PAID"

    delivered = await _order(client, admin_headers, order["id"])
    assert delivered["status"] == "DELIVERED"
    assert delivered["payment_status"] == "PAID"


async def test_the_cash_is_not_collected_before_delivery(
    client, admin_headers, customer_auth, order, payment
):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED"):
        moved = await _set_status(client, admin_headers, order["id"], value)
        assert moved.status_code == 200, moved.text

        assert (await _payment(client, customer_auth, payment["id"]))["status"] == "PENDING"
        assert (await _order(client, admin_headers, order["id"]))["payment_status"] == "PENDING"


async def test_cancelling_the_order_writes_the_payment_off(
    client, admin_headers, customer_auth, order, payment
):
    cancelled = await _set_status(client, admin_headers, order["id"], "CANCELLED")
    assert cancelled.status_code == 200, cancelled.text

    assert (await _payment(client, customer_auth, payment["id"]))["status"] == "FAILED"
    assert (await _order(client, admin_headers, order["id"]))["payment_status"] == "PENDING"


async def test_a_delivered_order_cannot_be_cancelled(
    client, admin_headers, customer_auth, order, payment
):
    await _deliver(client, admin_headers, order["id"])

    response = await _set_status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 409
    assert (await _payment(client, customer_auth, payment["id"]))["status"] == "PAID"


async def test_an_order_with_no_payment_can_still_be_delivered(
    client, admin_headers, session, tenant, order, payment
):
    """Delivery still works when the payment row is missing."""
    row = await PaymentRepository(session, tenant.id).get(UUID(payment["id"]))
    await session.delete(row)
    await session.commit()

    await _deliver(client, admin_headers, order["id"])

    delivered = await _order(client, admin_headers, order["id"])
    assert delivered["status"] == "DELIVERED"
    assert delivered["payment_status"] == "PENDING"
    assert delivered["payment"] is None


async def test_an_order_with_no_payment_can_still_be_cancelled(
    client, admin_headers, session, tenant, order, payment
):
    row = await PaymentRepository(session, tenant.id).get(UUID(payment["id"]))
    await session.delete(row)
    await session.commit()

    response = await _set_status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["payment"] is None


async def test_collecting_the_cash_leaves_inventory_alone(
    client, admin_headers, session, tenant, order, payment, variant
):
    """Delivering now touches the money too, which must not disturb the stock."""
    await _deliver(client, admin_headers, order["id"])

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0
    assert item.available_quantity == 8


async def test_writing_a_payment_off_still_returns_the_stock(
    client, admin_headers, session, tenant, order, payment, variant
):
    cancelled = await _set_status(client, admin_headers, order["id"], "CANCELLED")
    assert cancelled.status_code == 200, cancelled.text

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0
    assert item.available_quantity == 10


async def test_a_customer_reads_their_own_payment(client, customer_auth, payment):
    body = await _payment(client, customer_auth, payment["id"])

    assert body["id"] == payment["id"]
    assert body["order_id"] == payment["order_id"]


async def test_a_customer_cannot_read_another_customers_payment(
    client, payment, make_user, tenant
):
    intruder = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])

    response = await client.get(
        f"{PAYMENTS}/{payment['id']}", headers=headers_for(intruder)
    )

    assert response.status_code == 404


async def test_a_payment_from_another_tenant_is_not_found(
    other_client, payment, make_user, other_tenant
):
    outsider = await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_b"])

    response = await other_client.get(
        f"{PAYMENTS}/{payment['id']}", headers=headers_for(outsider)
    )

    assert response.status_code == 404


async def test_an_unknown_payment_is_not_found(client, customer_auth):
    response = await client.get(f"{PAYMENTS}/{uuid4()}", headers=customer_auth)

    assert response.status_code == 404


async def test_an_anonymous_caller_cannot_read_a_payment(client, payment):
    response = await client.get(f"{PAYMENTS}/{payment['id']}")

    assert response.status_code == 401


async def test_the_response_hides_internal_fields(client, customer_auth, payment):
    body = await _payment(client, customer_auth, payment["id"])

    assert "tenant_id" not in body
    assert "customer_id" not in body
    assert "updated_at" not in body


async def test_an_admin_lists_payments(client, admin_headers, payment):
    response = await client.get(ADMIN_PAYMENTS, headers=admin_headers)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["id"] for row in body["data"]] == [payment["id"]]
    assert body["meta"]["total_items"] == 1


async def test_an_admin_reads_one_payment(client, admin_headers, payment):
    response = await client.get(
        f"{ADMIN_PAYMENTS}/{payment['id']}", headers=admin_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["id"] == payment["id"]


async def test_payments_can_be_filtered_by_status(client, admin_headers, order, payment):
    await _deliver(client, admin_headers, order["id"])

    paid = await client.get(
        ADMIN_PAYMENTS, params={"status": "PAID"}, headers=admin_headers
    )
    pending = await client.get(
        ADMIN_PAYMENTS, params={"status": "PENDING"}, headers=admin_headers
    )

    assert paid.json()["meta"]["total_items"] == 1
    assert pending.json()["meta"]["total_items"] == 0


async def test_a_customer_may_not_reach_the_admin_payments_api(client, customer_auth, payment):
    listed = await client.get(ADMIN_PAYMENTS, headers=customer_auth)
    read = await client.get(f"{ADMIN_PAYMENTS}/{payment['id']}", headers=customer_auth)

    assert listed.status_code == 403
    assert read.status_code == 403


async def test_an_admin_cannot_set_a_payment_status(client, admin_headers, payment):
    """There is no write endpoint: cash is recorded by delivering the order."""
    response = await client.patch(
        f"{ADMIN_PAYMENTS}/{payment['id']}",
        json={"status": "PAID"},
        headers=admin_headers,
    )

    assert response.status_code == 405
