"""Reading orders back and moving them through fulfilment."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.catalogue.service import InventoryService
from tests.conftest import headers_for
from tests.orders.conftest import ADMIN_ORDERS, ORDERS


async def _status(client, headers, order_id, value):
    return await client.patch(
        f"{ADMIN_ORDERS}/{order_id}/status", json={"status": value}, headers=headers
    )


async def test_a_customer_lists_their_own_orders(client, customer_auth, order):
    response = await client.get(ORDERS, headers=customer_auth)

    assert response.status_code == 200, response.text
    body = response.json()
    assert [row["order_number"] for row in body["data"]] == [order["order_number"]]
    assert body["meta"]["total_items"] == 1


async def test_a_customer_reads_one_of_their_orders(client, customer_auth, order):
    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["order_number"] == order["order_number"]
    assert body["items"][0]["sku"].startswith("ORD-SKU-")
    assert body["delivery_address"]["city"] == "Bengaluru"


async def test_an_unknown_order_is_not_found(client, customer_auth, tenant):
    response = await client.get(f"{ORDERS}/{uuid4()}", headers=customer_auth)

    assert response.status_code == 404


async def test_the_response_hides_internal_fields(client, customer_auth, order):
    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)
    body = response.json()["data"]

    assert "tenant_id" not in body
    assert "customer_id" not in body
    assert "updated_at" not in body
    assert "order_id" not in body["items"][0]


async def test_staff_may_list_orders(client, staff_headers, order):
    response = await client.get(ADMIN_ORDERS, headers=staff_headers)

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["total_items"] == 1


async def test_staff_may_read_an_order(client, staff_headers, order):
    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}", headers=staff_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["order_number"] == order["order_number"]


async def test_orders_can_be_searched_by_order_number(client, admin_headers, order):
    response = await client.get(
        ADMIN_ORDERS, params={"order_number": order["order_number"]}, headers=admin_headers
    )

    assert response.json()["meta"]["total_items"] == 1


async def test_a_search_that_matches_nothing_is_empty(client, admin_headers, order):
    response = await client.get(
        ADMIN_ORDERS, params={"order_number": "ORD-999999"}, headers=admin_headers
    )

    assert response.json()["data"] == []


async def test_orders_can_be_filtered_by_status(client, admin_headers, order):
    pending = await client.get(
        ADMIN_ORDERS, params={"status": "PENDING"}, headers=admin_headers
    )
    shipped = await client.get(
        ADMIN_ORDERS, params={"status": "SHIPPED"}, headers=admin_headers
    )

    assert pending.json()["meta"]["total_items"] == 1
    assert shipped.json()["data"] == []


async def test_orders_can_be_filtered_by_payment_status(client, admin_headers, order):
    unpaid = await client.get(
        ADMIN_ORDERS, params={"payment_status": "PENDING"}, headers=admin_headers
    )
    paid = await client.get(
        ADMIN_ORDERS, params={"payment_status": "PAID"}, headers=admin_headers
    )

    assert unpaid.json()["meta"]["total_items"] == 1
    assert paid.json()["data"] == []


async def test_a_customer_may_not_reach_the_admin_orders_api(
    client, customer_auth, order
):
    response = await client.get(ADMIN_ORDERS, headers=customer_auth)

    assert response.status_code == 403


async def test_an_admin_moves_an_order_forward(client, admin_headers, order):
    response = await _status(client, admin_headers, order["id"], "CONFIRMED")

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "CONFIRMED"


async def test_the_full_happy_path(client, admin_headers, order):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"):
        response = await _status(client, admin_headers, order["id"], value)
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == value


async def test_a_backwards_step_is_refused(client, admin_headers, order):
    await _status(client, admin_headers, order["id"], "CONFIRMED")

    response = await _status(client, admin_headers, order["id"], "PENDING")

    assert response.status_code == 409
    assert "cannot become" in response.json()["message"]


async def test_a_delivered_order_is_final(client, admin_headers, order):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"):
        await _status(client, admin_headers, order["id"], value)

    response = await _status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 409


async def test_setting_the_same_status_changes_nothing(client, admin_headers, order):
    response = await _status(client, admin_headers, order["id"], "PENDING")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "PENDING"


async def test_staff_may_not_change_a_status(client, staff_headers, order):
    response = await _status(client, staff_headers, order["id"], "CONFIRMED")

    assert response.status_code == 403


async def test_a_customer_may_not_change_a_status(client, customer_auth, order):
    response = await _status(client, customer_auth, order["id"], "CONFIRMED")

    assert response.status_code == 403


async def test_payment_status_is_not_touched_by_fulfilment(
    client, admin_headers, order
):
    await _status(client, admin_headers, order["id"], "CONFIRMED")
    response = await _status(client, admin_headers, order["id"], "PROCESSING")

    assert response.json()["data"]["payment_status"] == "PENDING"


async def test_shipping_takes_the_stock_off_the_shelf(
    client, admin_headers, session, tenant, order, variant
):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED"):
        assert (await _status(client, admin_headers, order["id"], value)).status_code == 200

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0
    assert item.available_quantity == 8


async def test_cancelling_gives_the_stock_back(
    client, admin_headers, session, tenant, order, variant
):
    response = await _status(client, admin_headers, order["id"], "CANCELLED")
    assert response.status_code == 200, response.text

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0
    assert item.available_quantity == 10


async def test_a_processing_order_can_still_be_cancelled(
    client, admin_headers, session, tenant, order, variant
):
    await _status(client, admin_headers, order["id"], "CONFIRMED")
    await _status(client, admin_headers, order["id"], "PROCESSING")

    response = await _status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 200, response.text
    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0


async def test_a_shipped_order_cannot_be_cancelled(client, admin_headers, order):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED"):
        await _status(client, admin_headers, order["id"], value)

    response = await _status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 409


async def test_cancelling_an_already_cancelled_order_is_harmless(client, admin_headers, order):
    await _status(client, admin_headers, order["id"], "CANCELLED")

    response = await _status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CANCELLED"


async def test_an_unknown_status_is_refused(client, admin_headers, order):
    response = await _status(client, admin_headers, order["id"], "TELEPORTED")

    assert response.status_code == 422


async def _cancel(client, headers, order_id):
    return await client.post(f"{ORDERS}/{order_id}/cancel", headers=headers)


async def test_a_customer_cancels_their_own_pending_order(client, customer_auth, order):
    response = await _cancel(client, customer_auth, order["id"])

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "CANCELLED"


async def test_a_customer_may_still_cancel_a_confirmed_order(
    client, admin_headers, customer_auth, order
):
    await _status(client, admin_headers, order["id"], "CONFIRMED")

    response = await _cancel(client, customer_auth, order["id"])

    assert response.status_code == 200, response.text
    assert response.json()["data"]["status"] == "CANCELLED"


async def test_a_customer_may_not_cancel_once_it_is_being_packed(
    client, admin_headers, customer_auth, order
):
    await _status(client, admin_headers, order["id"], "PROCESSING")

    response = await _cancel(client, customer_auth, order["id"])

    assert response.status_code == 409
    assert "contact the store" in response.json()["message"]


async def test_an_admin_can_still_cancel_a_processing_order(
    client, admin_headers, customer_auth, order
):
    """What a customer may no longer do online, the shop still can."""
    await _status(client, admin_headers, order["id"], "PROCESSING")

    response = await _status(client, admin_headers, order["id"], "CANCELLED")

    assert response.status_code == 200, response.text


async def test_a_customer_may_not_cancel_a_shipped_order(
    client, admin_headers, customer_auth, order
):
    for value in ("PROCESSING", "SHIPPED"):
        await _status(client, admin_headers, order["id"], value)

    response = await _cancel(client, customer_auth, order["id"])

    assert response.status_code == 409


async def test_cancelling_twice_is_harmless(client, customer_auth, order):
    first = await _cancel(client, customer_auth, order["id"])
    second = await _cancel(client, customer_auth, order["id"])

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.json()["data"]["status"] == "CANCELLED"


async def test_a_customer_cannot_cancel_another_customers_order(
    client, order, make_user, tenant
):
    intruder = await make_user(tenant=tenant, phone="+919822229001")

    response = await _cancel(client, headers_for(intruder), order["id"])

    assert response.status_code == 404


async def test_cancelling_gives_the_stock_back_to_the_shelf(
    client, customer_auth, session, tenant, order, variant
):
    response = await _cancel(client, customer_auth, order["id"])
    assert response.status_code == 200, response.text

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0
    assert item.available_quantity == 10


async def test_an_anonymous_caller_cannot_cancel(client, order):
    response = await client.post(f"{ORDERS}/{order['id']}/cancel")

    assert response.status_code == 401


async def test_staff_may_not_use_the_customer_cancel_route(client, staff_headers, order):
    response = await _cancel(client, staff_headers, order["id"])

    assert response.status_code == 403
