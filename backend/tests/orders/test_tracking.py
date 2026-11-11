"""PACKED / OUT_FOR_DELIVERY / RETURNED, tracking numbers, courier events, public tracking."""

from __future__ import annotations

from uuid import UUID

from app.catalogue.service import InventoryService
from tests.orders.conftest import ADMIN_ORDERS, CUSTOMERS, ORDERS

TRACK = "/api/v1/storefront/orders/track"
DELIVERY_PHONE = "+919876500001"


async def test_the_full_journey_with_the_new_stops(order, set_status):
    for value in ("CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"):
        body = await set_status(order["id"], value)
        assert body["data"]["status"] == value


async def test_the_original_flow_still_works(order, set_status):
    for value in ("CONFIRMED", "PROCESSING", "SHIPPED", "DELIVERED"):
        await set_status(order["id"], value)


async def test_packed_can_follow_confirmed_directly(order, set_status):
    await set_status(order["id"], "CONFIRMED")

    body = await set_status(order["id"], "PACKED")

    assert body["data"]["status"] == "PACKED"


async def test_packed_can_move_directly_out_for_delivery_and_then_deliver(
    client, customer_auth, order, set_status
):
    await set_status(order["id"], "CONFIRMED")
    await set_status(order["id"], "PACKED")

    dispatched = await set_status(order["id"], "OUT_FOR_DELIVERY", note="Courier has parcel")
    delivered = await set_status(order["id"], "DELIVERED", note="Delivered to customer")
    events = (
        await client.get(f"{ORDERS}/{order['id']}/tracking", headers=customer_auth)
    ).json()["data"]["events"]

    assert dispatched["data"]["status"] == "OUT_FOR_DELIVERY"
    assert delivered["data"]["status"] == "DELIVERED"
    assert [event["status"] for event in events] == [
        "PENDING", "CONFIRMED", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"
    ]
    assert events[-1]["description"] == "Delivered to customer"


async def test_packed_can_deliver_directly_without_leaving_stock_reserved(
    session, tenant, order, set_status, variant
):
    await set_status(order["id"], "CONFIRMED")
    await set_status(order["id"], "PACKED")
    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    available_before_delivery = item.available_quantity

    delivered = await set_status(order["id"], "DELIVERED")
    await session.refresh(item)

    assert delivered["data"]["status"] == "DELIVERED"
    assert item.reserved_quantity == 0
    assert item.available_quantity == available_before_delivery - order["items"][0]["quantity"]


async def test_packed_cannot_skip_to_returned(order, set_status):
    await set_status(order["id"], "CONFIRMED")
    await set_status(order["id"], "PACKED")

    refused = await set_status(order["id"], "RETURNED", expect=409)

    assert "cannot become" in refused["message"]


async def test_a_packed_order_can_still_be_cancelled(
    session, tenant, order, set_status, variant
):
    for value in ("CONFIRMED", "PACKED", "CANCELLED"):
        await set_status(order["id"], value)

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    await session.refresh(item)
    assert item.reserved_quantity == 0


async def test_out_for_delivery_cannot_go_back(order, set_status):
    for value in ("CONFIRMED", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY"):
        await set_status(order["id"], value)

    body = await set_status(order["id"], "SHIPPED", expect=409)

    assert "cannot become" in body["message"]


async def test_an_undelivered_parcel_is_returned_and_restocked(
    session, tenant, order, set_status, variant
):
    for value in ("CONFIRMED", "PACKED", "SHIPPED"):
        await set_status(order["id"], value)

    body = await set_status(order["id"], "RETURNED")

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    await session.refresh(item)
    assert body["data"]["status"] == "RETURNED"
    assert item.available_quantity == 10
    assert body["data"]["payment"]["status"] == "FAILED"


async def test_a_pending_order_cannot_be_returned(order, set_status):
    await set_status(order["id"], "RETURNED", expect=409)


async def test_shipping_records_the_tracking_number(order, set_status):
    for value in ("CONFIRMED", "PACKED"):
        await set_status(order["id"], value)

    body = await set_status(
        order["id"],
        "SHIPPED",
        courier_name="Delhivery",
        tracking_number="AWB123456",
        tracking_url="https://track.example.com/AWB123456",
    )

    assert body["data"]["shipment"] == {
        "courier_name": "Delhivery",
        "tracking_number": "AWB123456",
        "tracking_url": "https://track.example.com/AWB123456",
    }


async def test_an_admin_updates_the_shipment_separately(client, admin_headers, order):
    response = await client.patch(
        f"{ADMIN_ORDERS}/{order['id']}/shipment",
        json={"tracking_number": "AWB999"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["shipment"]["tracking_number"] == "AWB999"


async def test_a_customer_cannot_set_tracking(client, customer_auth, order):
    response = await client.patch(
        f"{ADMIN_ORDERS}/{order['id']}/shipment",
        json={"tracking_number": "AWB999"},
        headers=customer_auth,
    )

    assert response.status_code == 403


async def test_the_timeline_lists_every_step_and_courier_scan(
    client, admin_headers, customer_auth, order, set_status
):
    for value in ("CONFIRMED", "PACKED", "SHIPPED"):
        await set_status(order["id"], value)
    scan = await client.post(
        f"{ADMIN_ORDERS}/{order['id']}/tracking-events",
        json={"description": "Arrived at Kochi hub", "location": "Kochi"},
        headers=admin_headers,
    )

    response = await client.get(f"{ORDERS}/{order['id']}/tracking", headers=customer_auth)

    events = response.json()["data"]["events"]
    assert scan.status_code == 201
    assert [e["status"] for e in events] == ["PENDING", "CONFIRMED", "PACKED", "SHIPPED", None]
    assert events[-1]["location"] == "Kochi"
    assert events[-1]["source"] == "ADMIN"


async def test_a_status_note_becomes_the_event_description(client, customer_auth, order, set_status):
    await set_status(order["id"], "CONFIRMED", note="Confirmed on call")

    events = (
        await client.get(f"{ORDERS}/{order['id']}/tracking", headers=customer_auth)
    ).json()["data"]["events"]

    assert events[-1]["description"] == "Confirmed on call"


async def test_public_tracking_needs_the_matching_phone(client, order):
    by_delivery_phone = await client.get(
        TRACK, params={"order_number": order["order_number"], "phone": DELIVERY_PHONE}
    )
    by_account_phone = await client.get(
        TRACK, params={"order_number": order["order_number"], "phone": CUSTOMERS["buyer"]}
    )
    wrong_phone = await client.get(
        TRACK, params={"order_number": order["order_number"], "phone": "+919999999999"}
    )
    wrong_number = await client.get(
        TRACK, params={"order_number": "ORD-1", "phone": DELIVERY_PHONE}
    )

    assert by_delivery_phone.status_code == 200
    assert by_delivery_phone.json()["data"]["status"] == "PENDING"
    assert by_account_phone.status_code == 200
    assert wrong_phone.status_code == 404
    assert wrong_number.status_code == 404


async def test_another_customers_tracking_is_not_found(
    client, make_user, tenant, order
):
    from tests.conftest import headers_for

    stranger = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["intruder"]))

    response = await client.get(f"{ORDERS}/{order['id']}/tracking", headers=stranger)

    assert response.status_code == 404


async def test_customers_also_bought_comes_from_real_orders(
    client, admin_headers, customer_auth, new_variant, add_to_cart, address, place_order
):
    first = await new_variant()
    second = await new_variant()
    await add_to_cart(customer_auth, first["id"], 1)
    await add_to_cart(customer_auth, second["id"], 1)
    assert (await place_order(customer_auth, address["id"])).status_code == 201

    response = await client.get(
        f"/api/v1/storefront/products/{first['product_id']}/related"
    )

    bought = [p["id"] for p in response.json()["data"]["customers_also_bought"]]
    assert bought == [second["product_id"]]
