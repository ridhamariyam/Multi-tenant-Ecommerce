"""Cash-on-delivery controls: switch, limits, fee, pincodes, blacklist, advance, report."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select

from app.payments.models import Payment
from tests.orders.conftest import CHECKOUT, CUSTOMERS

API = "/api/v1"
COD = f"{API}/admin/cod"
PAYMENTS = f"{API}/admin/payments"
PINCODES = f"{API}/admin/pincodes"


async def _cod(client, headers, **settings):
    response = await client.put(f"{COD}/settings", json=settings, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def _ready(customer_auth, variant, add_to_cart, save_address, quantity=1, **address):
    await add_to_cart(customer_auth, variant["id"], quantity)
    return await save_address(customer_auth, **address)


async def test_cod_is_on_with_no_limits_when_never_configured(client, admin_headers):
    response = await client.get(f"{COD}/settings", headers=admin_headers)

    assert response.json()["data"]["is_enabled"] is True
    assert Decimal(response.json()["data"]["fee_amount"]) == Decimal("0.00")


async def test_switching_cod_off_blocks_orders(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await _cod(client, admin_headers, is_enabled=False)
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    preview = await client.post(
        f"{CHECKOUT}/preview", json={"address_id": address["id"]}, headers=customer_auth
    )
    response = await place_order(customer_auth, address["id"])

    assert preview.json()["data"]["cod"]["available"] is False
    assert preview.json()["data"]["cod"]["reason"] == "DISABLED"
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "COD_UNAVAILABLE"


async def test_an_order_above_the_limit_cannot_be_cod(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await _cod(client, admin_headers, max_order_amount="1500.00")
    address = await _ready(customer_auth, variant, add_to_cart, save_address, quantity=2)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert "above" in response.json()["message"]


async def test_an_order_below_the_minimum_cannot_be_cod(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await _cod(client, admin_headers, min_order_amount="5000.00")
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409


async def test_the_cod_fee_is_added_to_the_total(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await _cod(client, admin_headers, fee_amount="50.00")
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    order = (await place_order(customer_auth, address["id"])).json()["data"]

    assert Decimal(order["cod_fee"]) == Decimal("50.00")
    assert Decimal(order["total_amount"]) == (
        Decimal(order["subtotal"])
        - Decimal(order["discount_amount"])
        + Decimal(order["shipping_amount"])
        + Decimal(order["cod_fee"])
        + Decimal(order["tax_amount"])
    )
    assert Decimal(order["payment"]["amount"]) == Decimal(order["total_amount"])


async def test_a_pincode_can_refuse_cod(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await client.put(f"{PINCODES}/560025", json={"cod_available": False}, headers=admin_headers)
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert "pincode" in response.json()["message"]


async def test_a_blacklisted_customer_phone_cannot_use_cod(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await client.post(
        f"{COD}/blacklist", json={"phone": CUSTOMERS["buyer"], "reason": "Refused twice"},
        headers=admin_headers,
    )
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert "phone" in response.json()["message"]


async def test_a_blacklisted_delivery_phone_cannot_use_cod(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await client.post(f"{COD}/blacklist", json={"phone": "9876500001"}, headers=admin_headers)
    address = await _ready(customer_auth, variant, add_to_cart, save_address)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409


async def test_the_blacklist_is_managed_by_admins(client, admin_headers, staff_headers):
    created = await client.post(f"{COD}/blacklist", json={"phone": "+919000000001"}, headers=admin_headers)
    duplicate = await client.post(f"{COD}/blacklist", json={"phone": "9000000001"}, headers=admin_headers)
    by_staff = await client.post(f"{COD}/blacklist", json={"phone": "+919000000002"}, headers=staff_headers)
    listed = await client.get(f"{COD}/blacklist", headers=staff_headers)
    removed = await client.delete(f"{COD}/blacklist/{created.json()['data']['id']}", headers=admin_headers)

    assert created.status_code == 201
    assert created.json()["data"]["source"] == "MANUAL"
    assert duplicate.status_code == 409
    assert by_staff.status_code == 403
    assert len(listed.json()["data"]) == 1
    assert removed.status_code == 204


async def test_repeated_undelivered_orders_auto_blacklist_the_phone(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, auto_blacklist_threshold=2)

    for _ in range(2):
        order = await order_in(customer_auth)
        for status in ("CONFIRMED", "PACKED", "SHIPPED", "RETURNED"):
            await set_status(order["id"], status)

    listed = (await client.get(f"{COD}/blacklist", headers=admin_headers)).json()["data"]
    assert {entry["source"] for entry in listed} == {"AUTO"}
    assert CUSTOMERS["buyer"] in {entry["phone"] for entry in listed}


async def test_one_undelivered_order_is_below_the_threshold(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, auto_blacklist_threshold=2)
    order = await order_in(customer_auth)
    for status in ("CONFIRMED", "PACKED", "SHIPPED", "RETURNED"):
        await set_status(order["id"], status)

    listed = (await client.get(f"{COD}/blacklist", headers=admin_headers)).json()["data"]
    assert listed == []


async def test_an_advance_splits_the_payment(
    client, admin_headers, customer_auth, order_in
):
    await _cod(client, admin_headers, advance_amount="100.00")

    order = await order_in(customer_auth)

    purposes = {p["purpose"]: p for p in order["payments"]}
    assert Decimal(order["advance_amount"]) == Decimal("100.00")
    assert purposes["ADVANCE"]["provider"] == "PREPAID"
    assert Decimal(purposes["ADVANCE"]["amount"]) == Decimal("100.00")
    assert Decimal(purposes["BALANCE"]["amount"]) == Decimal(order["total_amount"]) - Decimal("100.00")
    assert order["payment"]["purpose"] == "BALANCE"


async def test_an_order_waits_for_its_advance(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, advance_amount="100.00")
    order = await order_in(customer_auth)
    advance = next(p for p in order["payments"] if p["purpose"] == "ADVANCE")

    blocked = await set_status(order["id"], "CONFIRMED", expect=409)
    paid = await client.post(f"{PAYMENTS}/{advance['id']}/mark-paid", headers=admin_headers)
    confirmed = await set_status(order["id"], "CONFIRMED")

    assert blocked["error"]["code"] == "ADVANCE_PENDING"
    assert paid.json()["data"]["status"] == "PAID"
    assert confirmed["data"]["payment_status"] == "PARTIALLY_PAID"


async def test_delivery_settles_the_balance(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, advance_amount="100.00")
    order = await order_in(customer_auth)
    advance = next(p for p in order["payments"] if p["purpose"] == "ADVANCE")
    await client.post(f"{PAYMENTS}/{advance['id']}/mark-paid", headers=admin_headers)

    for status in ("CONFIRMED", "PACKED", "SHIPPED"):
        await set_status(order["id"], status)
    delivered = await set_status(order["id"], "DELIVERED")

    assert delivered["data"]["payment_status"] == "PAID"
    assert {p["status"] for p in delivered["data"]["payments"]} == {"PAID"}


async def test_packed_cannot_skip_cod_advance_when_delivering(
    session, client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, advance_amount="100.00")
    order = await order_in(customer_auth)
    advance = next(p for p in order["payments"] if p["purpose"] == "ADVANCE")
    await client.post(f"{PAYMENTS}/{advance['id']}/mark-paid", headers=admin_headers)
    await set_status(order["id"], "CONFIRMED")
    await set_status(order["id"], "PACKED")
    # An unpaid advance after packing must still block the newly supported direct path.
    # Reversing the payment status here mirrors an unsettled advance record.
    payment = await session.scalar(select(Payment).where(Payment.id == UUID(advance["id"])))
    payment.status = "PENDING"
    await session.commit()

    refused = await set_status(order["id"], "DELIVERED", expect=409)
    assert refused["error"]["code"] == "ADVANCE_PENDING"


async def test_only_an_advance_can_be_marked_paid_by_hand(
    client, admin_headers, customer_auth, order_in
):
    order = await order_in(customer_auth)

    response = await client.post(
        f"{PAYMENTS}/{order['payment']['id']}/mark-paid", headers=admin_headers
    )

    assert response.status_code == 409


async def test_an_advance_is_recorded_once_and_never_on_a_cancelled_order(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, advance_amount="100.00")
    paid_order = await order_in(customer_auth)
    paid_advance = next(p for p in paid_order["payments"] if p["purpose"] == "ADVANCE")
    url = f"{PAYMENTS}/{paid_advance['id']}/mark-paid"
    await client.post(url, headers=admin_headers)

    repeated = await client.post(url, headers=admin_headers)

    cancelled_order = await order_in(customer_auth)
    advance = next(p for p in cancelled_order["payments"] if p["purpose"] == "ADVANCE")
    await set_status(cancelled_order["id"], "CANCELLED")
    refused = await client.post(f"{PAYMENTS}/{advance['id']}/mark-paid", headers=admin_headers)

    assert repeated.status_code == 409
    assert refused.status_code == 409


async def test_the_cod_report_counts_and_sums(
    client, admin_headers, customer_auth, order_in, set_status
):
    await _cod(client, admin_headers, fee_amount="50.00")
    delivered = await order_in(customer_auth)
    returned = await order_in(customer_auth)
    await order_in(customer_auth)
    for status in ("CONFIRMED", "PACKED", "SHIPPED", "DELIVERED"):
        await set_status(delivered["id"], status)
    for status in ("CONFIRMED", "PACKED", "SHIPPED", "RETURNED"):
        await set_status(returned["id"], status)
    today = date.today().isoformat()

    report = (
        await client.get(
            f"{COD}/report", params={"start_date": today, "end_date": today}, headers=admin_headers
        )
    ).json()["data"]

    assert report["total_orders"] == 3
    assert report["delivered_orders"] == 1
    assert report["returned_orders"] == 1
    assert report["in_progress_orders"] == 1
    assert report["delivery_rate"] == 50.0
    assert Decimal(report["cash_collected"]) == Decimal(delivered["total_amount"])
    assert Decimal(report["fees_collected"]) == Decimal("50.00")
    assert Decimal(report["net_revenue"]) == Decimal(delivered["total_amount"])


async def test_cod_settings_validate_limits(client, admin_headers):
    response = await client.put(
        f"{COD}/settings",
        json={"min_order_amount": "500.00", "max_order_amount": "100.00"},
        headers=admin_headers,
    )

    assert response.status_code == 422
