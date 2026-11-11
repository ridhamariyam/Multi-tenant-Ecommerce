"""Turning a cart into an order."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

from app.catalogue.service import InventoryService
from tests.catalogue.factories import inventory_url
from tests.conftest import headers_for
from tests.helpers import run_concurrently, succeeded
from tests.orders.conftest import CHECKOUT, CUSTOMERS


async def _sellable(client, admin_headers, variant_id) -> int:
    response = await client.get(inventory_url(variant_id), headers=admin_headers)
    return response.json()["data"]["sellable_quantity"]


async def test_a_preview_prices_the_cart(client, customer_auth, variant, add_to_cart):
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await client.post(f"{CHECKOUT}/preview", headers=customer_auth)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert body["subtotal"] == "1998.00"
    assert body["shipping_amount"] == "0.00"
    assert body["total_amount"] == "1998.00"
    assert body["items"][0]["unit_price"] == "999.00"
    assert body["items"][0]["quantity"] == 2


async def test_a_preview_reserves_nothing(
    client, customer_auth, admin_headers, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 2)
    before = await _sellable(client, admin_headers, variant["id"])

    await client.post(f"{CHECKOUT}/preview", headers=customer_auth)

    assert await _sellable(client, admin_headers, variant["id"]) == before


async def test_a_preview_accepts_the_address_it_will_be_delivered_to(
    client, customer_auth, address, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"address_id": address["id"]},
        headers=customer_auth,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["subtotal"] == "1998.00"


async def test_a_preview_refuses_an_address_that_does_not_exist(
    client, customer_auth, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"address_id": str(uuid4())},
        headers=customer_auth,
    )

    assert response.status_code == 404


async def test_a_preview_refuses_another_customers_address(
    client, customer_auth, make_user, tenant, save_address, variant, add_to_cart
):
    stranger = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])
    theirs = await save_address(headers_for(stranger))
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"address_id": theirs["id"]},
        headers=customer_auth,
    )

    assert response.status_code == 404


async def test_previewing_an_empty_cart_is_refused(client, customer_auth, tenant):
    response = await client.post(f"{CHECKOUT}/preview", headers=customer_auth)

    assert response.status_code == 409
    assert "empty" in response.json()["message"].lower()


async def test_an_order_is_created_from_the_cart(
    client, customer_auth, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 201, response.text
    body = response.json()["data"]
    assert body["status"] == "PENDING"
    assert body["payment_status"] == "PENDING"
    assert body["total_amount"] == "1998.00"
    assert len(body["items"]) == 1


async def test_the_order_number_is_readable_and_not_a_uuid(order):
    assert order["order_number"].startswith("ORD-")
    assert int(order["order_number"].removeprefix("ORD-")) >= 100001


async def test_order_numbers_do_not_repeat(
    client, customer_auth, address, new_variant, add_to_cart, place_order
):
    numbers = []
    for _ in range(3):
        variant = await new_variant()
        await add_to_cart(customer_auth, variant["id"], 1)
        response = await place_order(customer_auth, address["id"])
        numbers.append(response.json()["data"]["order_number"])

    assert len(set(numbers)) == 3


async def test_placing_an_order_reserves_the_stock(
    client, customer_auth, admin_headers, address, variant, add_to_cart, place_order
):
    before = await _sellable(client, admin_headers, variant["id"])
    await add_to_cart(customer_auth, variant["id"], 3)

    await place_order(customer_auth, address["id"])

    assert await _sellable(client, admin_headers, variant["id"]) == before - 3


async def test_the_address_is_copied_onto_the_order(order, address):
    delivery = order["delivery_address"]

    assert delivery["full_name"] == address["full_name"]
    assert delivery["city"] == address["city"]
    assert delivery["postal_code"] == address["postal_code"]


async def test_editing_the_address_later_does_not_change_the_order(
    client, customer_auth, order, address
):
    await client.patch(
        f"/api/v1/addresses/{address['id']}",
        json={"city": "Somewhere Else"},
        headers=customer_auth,
    )

    response = await client.get(
        f"/api/v1/orders/{order['id']}", headers=customer_auth
    )
    assert response.json()["data"]["delivery_address"]["city"] == address["city"]


async def test_deleting_the_address_later_does_not_change_the_order(
    client, customer_auth, order, address
):
    deleted = await client.delete(
        f"/api/v1/addresses/{address['id']}", headers=customer_auth
    )
    assert deleted.status_code == 204

    response = await client.get(
        f"/api/v1/orders/{order['id']}", headers=customer_auth
    )
    assert response.status_code == 200
    assert response.json()["data"]["delivery_address"]["city"] == address["city"]


async def test_a_later_price_change_does_not_change_the_order(
    client, admin_headers, customer_auth, order, variant
):
    await client.patch(
        f"/api/v1/catalogue/variants/{variant['id']}",
        json={"price": "1199.00"},
        headers=admin_headers,
    )

    response = await client.get(
        f"/api/v1/orders/{order['id']}", headers=customer_auth
    )
    body = response.json()["data"]
    assert body["items"][0]["unit_price"] == "999.00"
    assert body["total_amount"] == "1998.00"


async def test_a_later_rename_does_not_change_the_order(
    client, admin_headers, customer_auth, order, variant
):
    original = order["items"][0]["product_name"]
    await client.patch(
        f"/api/v1/catalogue/products/{order['items'][0]['product_id']}",
        json={"name": "Renamed Product"},
        headers=admin_headers,
    )

    response = await client.get(
        f"/api/v1/orders/{order['id']}", headers=customer_auth
    )
    assert response.json()["data"]["items"][0]["product_name"] == original


async def test_the_cart_is_marked_converted(session, order, customer):
    from app.cart.repository import CartRepository
    from app.orders.repository import OrderRepository

    placed = await OrderRepository(session, customer.tenant_id).get(
        UUID(order["id"])
    )
    assert placed is not None

    active = await CartRepository(session, customer.tenant_id).get_active(customer.id)
    assert active is None


async def test_a_converted_cart_cannot_be_checked_out_again(
    client, customer_auth, order, address, place_order
):
    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409


async def test_the_next_add_to_cart_starts_a_fresh_cart(
    client, customer_auth, order, new_variant, add_to_cart
):
    variant = await new_variant()

    cart = await add_to_cart(customer_auth, variant["id"], 1)

    assert cart["id"] != order["id"]
    assert cart["item_count"] == 1


async def test_an_empty_cart_cannot_be_ordered(
    client, customer_auth, address, place_order, tenant
):
    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409


async def test_an_unknown_address_is_not_found(
    client, customer_auth, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await place_order(customer_auth, uuid4())

    assert response.status_code == 404


async def test_another_customers_address_cannot_be_used(
    client, customer_auth, variant, add_to_cart, place_order, save_address,
    make_user, tenant,
):
    intruder = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])
    theirs = await save_address(headers_for(intruder))

    await add_to_cart(customer_auth, variant["id"], 1)
    response = await place_order(customer_auth, theirs["id"])

    assert response.status_code == 404


async def test_an_archived_variant_blocks_checkout(
    client, admin_headers, customer_auth, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 1)
    await client.delete(
        f"/api/v1/catalogue/variants/{variant['id']}", headers=admin_headers
    )

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert "no longer available" in response.json()["message"]


async def test_stock_sold_out_after_adding_blocks_checkout(
    client, admin_headers, customer_auth, address, new_variant, add_to_cart, place_order
):
    variant = await new_variant(initial_quantity=5)
    await add_to_cart(customer_auth, variant["id"], 5)

    await client.put(
        inventory_url(variant["id"]), json={"available_quantity": 2}, headers=admin_headers
    )

    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INSUFFICIENT_STOCK"


async def test_prices_are_never_taken_from_the_request(
    client, customer_auth, address, variant, add_to_cart, place_order
):
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await client.post(
        CHECKOUT,
        json={
            "address_id": str(address["id"]),
            "total_amount": "1.00",
            "subtotal": "1.00",
        },
        headers=customer_auth,
    )

    assert response.status_code == 422
    placed = await place_order(customer_auth, address["id"])
    assert placed.json()["data"]["total_amount"] == "999.00"


async def test_a_failed_checkout_reserves_nothing(
    client, admin_headers, customer_auth, address, new_variant, add_to_cart, place_order
):
    """Two lines, the second unsatisfiable: the first must not stay reserved."""
    good = await new_variant(initial_quantity=10)
    short = await new_variant(initial_quantity=5)

    await add_to_cart(customer_auth, good["id"], 2)
    await add_to_cart(customer_auth, short["id"], 5)

    await client.put(
        inventory_url(short["id"]), json={"available_quantity": 1}, headers=admin_headers
    )

    before = await _sellable(client, admin_headers, good["id"])
    response = await place_order(customer_auth, address["id"])

    assert response.status_code == 409
    assert await _sellable(client, admin_headers, good["id"]) == before


async def test_a_failed_checkout_creates_no_order(
    client, customer_auth, address, new_variant, add_to_cart, place_order, admin_headers
):
    variant = await new_variant(initial_quantity=5)
    await add_to_cart(customer_auth, variant["id"], 5)
    await client.put(
        inventory_url(variant["id"]), json={"available_quantity": 0}, headers=admin_headers
    )

    failed = await place_order(customer_auth, address["id"])
    assert failed.status_code == 409

    listing = await client.get("/api/v1/orders", headers=customer_auth)
    assert listing.json()["data"] == []


async def test_only_one_of_two_racing_checkouts_can_take_the_last_units(
    engine, session, tenant, make_user, client, admin_headers, new_variant,
    add_to_cart, save_address,
):
    """Stock of 10, two customers each wanting 6: exactly one may win."""
    variant = await new_variant(initial_quantity=10)

    racers = []
    for key in ("racer_one", "racer_two"):
        user = await make_user(tenant=tenant, phone=CUSTOMERS[key])
        headers = headers_for(user)
        await add_to_cart(headers, variant["id"], 6)
        address = await save_address(headers)
        racers.append((user, address))

    async def checkout(db, index):
        from app.orders.service import CheckoutService

        user, address = racers[index]
        return await CheckoutService(db, tenant.id, user.id).place_order(
            UUID(address["id"])
        )

    results = await run_concurrently(engine, 2, checkout)

    assert len(succeeded(results)) == 1

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 6
    assert Decimal(item.available_quantity) == 10
