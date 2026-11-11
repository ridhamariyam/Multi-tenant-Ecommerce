"""What checkout charges, and what the order freezes onto itself."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from app.catalogue.serializers import sellable_quantity
from app.catalogue.service import InventoryService
from tests.pricing.conftest import ADMIN_ORDERS, ADMIN_PAYMENTS, CHECKOUT, ORDERS


async def test_the_preview_reports_every_amount(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    body = await preview()

    assert Decimal(body["subtotal"]) == Decimal("2000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["tax_amount"]) == Decimal("378.00")
    assert Decimal(body["total_amount"]) == Decimal("2478.00")


async def test_the_total_is_the_sum_of_its_parts(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(3)

    body = await preview()

    assert Decimal(body["total_amount"]) == (
        Decimal(body["subtotal"])
        + Decimal(body["shipping_amount"])
        + Decimal(body["tax_amount"])
    )


async def test_the_preview_reserves_nothing(
    session, tenant, set_shipping, set_tax, fill_cart, preview, variant
):
    await set_shipping()
    await set_tax()
    await fill_cart(2)

    await preview()

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 0


async def test_the_frontend_cannot_override_shipping(
    client, customer_auth, set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"shipping_amount": "0.00", "subtotal": "1.00"},
        headers=customer_auth,
    )

    assert response.status_code == 422
    body = await preview()
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["subtotal"]) == Decimal("2000.00")


async def test_the_frontend_cannot_override_tax(
    client, customer_auth, set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    response = await client.post(
        f"{CHECKOUT}/preview",
        json={"tax_amount": "0.00", "total_amount": "1.00"},
        headers=customer_auth,
    )

    assert response.status_code == 422
    body = await preview()
    assert Decimal(body["tax_amount"]) == Decimal("378.00")
    assert Decimal(body["total_amount"]) == Decimal("2478.00")


async def test_a_placed_order_rejects_amounts_in_the_body(
    client, customer_auth, address, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    response = await client.post(
        CHECKOUT,
        json={"address_id": address["id"], "subtotal": "1.00", "total_amount": "1.00"},
        headers=customer_auth,
    )

    assert response.status_code == 422

    order = await place_order()
    assert Decimal(order["subtotal"]) == Decimal("2000.00")
    assert Decimal(order["shipping_amount"]) == Decimal("100.00")
    assert Decimal(order["tax_amount"]) == Decimal("378.00")
    assert Decimal(order["total_amount"]) == Decimal("2478.00")


async def test_the_order_stores_every_amount(
    client, customer_auth, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)
    order = await place_order()

    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)

    body = response.json()["data"]
    assert Decimal(body["subtotal"]) == Decimal("2000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["tax_amount"]) == Decimal("378.00")
    assert Decimal(body["total_amount"]) == Decimal("2478.00")


async def test_the_preview_and_the_order_agree(
    set_shipping, set_tax, fill_cart, preview, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    quoted = await preview()
    order = await place_order()

    for field in ("subtotal", "shipping_amount", "tax_amount", "total_amount"):
        assert Decimal(order[field]) == Decimal(quoted[field]), field


async def test_a_later_tax_change_does_not_rewrite_an_old_order(
    client, customer_auth, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)
    order = await place_order()

    await set_tax(tax_percentage="20.00")

    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)

    body = response.json()["data"]
    assert Decimal(body["tax_amount"]) == Decimal("378.00")
    assert Decimal(body["total_amount"]) == Decimal("2478.00")


async def test_a_later_shipping_change_does_not_rewrite_an_old_order(
    client, customer_auth, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax(tax_percentage="0.00")
    await fill_cart(2)
    order = await place_order()

    await set_shipping(shipping_amount="500.00", free_shipping_minimum=None)

    response = await client.get(f"{ORDERS}/{order['id']}", headers=customer_auth)

    body = response.json()["data"]
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["total_amount"]) == Decimal("2100.00")


async def test_an_admin_sees_the_same_amounts(
    client, admin_headers, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)
    order = await place_order()

    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}", headers=admin_headers)

    assert Decimal(response.json()["data"]["tax_amount"]) == Decimal("378.00")


async def test_checkout_still_reserves_inventory(
    session, tenant, set_shipping, set_tax, fill_cart, place_order, variant
):
    await set_shipping()
    await set_tax()
    await fill_cart(2)

    await place_order()

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))
    assert item.reserved_quantity == 2
    assert item.available_quantity == 20
    assert sellable_quantity(item) == 18


async def test_checkout_still_creates_the_cod_payment(
    client, admin_headers, set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)
    order = await place_order()

    response = await client.get(
        ADMIN_PAYMENTS, params={"order_id": order["id"]}, headers=admin_headers
    )

    assert response.json()["meta"]["total_items"] == 1
    payment = response.json()["data"][0]
    assert payment["provider"] == "COD"
    assert payment["status"] == "PENDING"
    assert Decimal(payment["amount"]) == Decimal("2478.00")


async def test_free_shipping_carries_through_to_the_order(
    set_shipping, set_tax, fill_cart, place_order
):
    await set_shipping()
    await set_tax()
    await fill_cart(2)

    order = await place_order()

    assert Decimal(order["shipping_amount"]) == Decimal("0.00")
    assert Decimal(order["tax_amount"]) == Decimal("360.00")
    assert Decimal(order["total_amount"]) == Decimal("2360.00")
