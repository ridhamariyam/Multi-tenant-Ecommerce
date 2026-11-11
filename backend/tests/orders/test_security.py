"""Isolation for orders and addresses; anything else reads as not found."""

from __future__ import annotations

from tests.catalogue.factories import make_category, make_product, make_variant
from tests.conftest import headers_for
from tests.orders.conftest import (
    ADDRESSES,
    ADMIN_ORDERS,
    CHECKOUT,
    CUSTOMERS,
    ORDERS,
    address_payload,
)


async def _order_for(client, headers, variant_id, cart_route="/api/v1/cart"):
    """Save an address, fill a cart and check out, all as one customer."""
    saved = await client.post(ADDRESSES, json=address_payload(), headers=headers)
    assert saved.status_code == 201, saved.text

    added = await client.post(
        cart_route + "/items",
        json={"variant_id": variant_id, "quantity": 1},
        headers=headers,
    )
    assert added.status_code == 201, added.text

    placed = await client.post(
        CHECKOUT, json={"address_id": saved.json()["data"]["id"]}, headers=headers
    )
    assert placed.status_code == 201, placed.text
    return placed.json()["data"]


async def test_another_customers_order_is_not_found(
    client, order, make_user, tenant
):
    intruder = await make_user(tenant=tenant, phone=CUSTOMERS["intruder"])

    response = await client.get(
        f"{ORDERS}/{order['id']}", headers=headers_for(intruder)
    )

    assert response.status_code == 404


async def test_a_listing_never_shows_another_customers_orders(
    client, order, make_user, tenant
):
    intruder = await make_user(tenant=tenant, phone="+919822223001")

    response = await client.get(ORDERS, headers=headers_for(intruder))

    assert response.json()["data"] == []


async def test_each_customer_sees_only_their_own_order(
    client, tenant, make_user, new_variant
):
    first = await make_user(tenant=tenant, phone="+919822223002")
    second = await make_user(tenant=tenant, phone="+919822223003")

    mine = await _order_for(client, headers_for(first), (await new_variant())["id"])
    theirs = await _order_for(client, headers_for(second), (await new_variant())["id"])

    listing = await client.get(ORDERS, headers=headers_for(first))
    numbers = [row["order_number"] for row in listing.json()["data"]]

    assert numbers == [mine["order_number"]]
    assert theirs["order_number"] not in numbers


async def test_an_order_from_another_tenant_is_not_found_for_a_customer(
    client, other_client, tenant, other_tenant, make_user, new_variant
):
    ours = await make_user(tenant=tenant, phone=CUSTOMERS["tenant_a"])
    order = await _order_for(client, headers_for(ours), (await new_variant())["id"])

    theirs = await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_b"])
    response = await other_client.get(
        f"{ORDERS}/{order['id']}", headers=headers_for(theirs)
    )

    assert response.status_code == 404


async def test_an_order_from_another_tenant_is_not_found_for_an_admin(
    client, other_client, order, other_admin_headers
):
    response = await other_client.get(
        f"{ADMIN_ORDERS}/{order['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_an_admin_listing_only_shows_their_own_tenants_orders(
    client, other_client, order, other_admin_headers
):
    response = await other_client.get(ADMIN_ORDERS, headers=other_admin_headers)

    assert response.json()["data"] == []


async def test_another_tenants_order_status_cannot_be_changed(
    other_client, order, other_admin_headers
):
    response = await other_client.patch(
        f"{ADMIN_ORDERS}/{order['id']}/status",
        json={"status": "CONFIRMED"},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_a_token_from_one_tenant_is_useless_at_another(
    other_client, customer_auth, other_tenant
):
    response = await other_client.get(ORDERS, headers=customer_auth)

    assert response.status_code == 401


async def test_an_address_from_another_tenant_is_not_found(
    client, other_client, address, other_tenant, make_user
):
    theirs = await make_user(tenant=other_tenant, phone="+919822223004")

    response = await other_client.get(
        f"{ADDRESSES}/{address['id']}", headers=headers_for(theirs)
    )

    assert response.status_code == 404


async def test_an_address_from_another_tenant_cannot_be_delivered_to(
    client, other_client, address, other_tenant, other_admin_headers, make_user
):
    """An address id from the wrong tenant must not become a delivery snapshot."""
    buyer = await make_user(tenant=other_tenant, phone="+919822223005")
    headers = headers_for(buyer)

    category = await make_category(other_client, other_admin_headers)
    product = await make_product(
        other_client, other_admin_headers, category["id"], status="ACTIVE"
    )
    variant = await make_variant(
        other_client,
        other_admin_headers,
        product["id"],
        sku="OTHER-SKU-1",
        status="ACTIVE",
        initial_quantity=5,
    )

    added = await other_client.post(
        "/api/v1/cart/items",
        json={"variant_id": variant["id"], "quantity": 1},
        headers=headers,
    )
    assert added.status_code == 201, added.text

    response = await other_client.post(
        CHECKOUT, json={"address_id": address["id"]}, headers=headers
    )

    assert response.status_code == 404


async def test_a_tenant_id_in_the_body_is_rejected(
    client, customer_auth, address, variant, add_to_cart, other_tenant, place_order
):
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await client.post(
        CHECKOUT,
        json={"address_id": address["id"], "tenant_id": str(other_tenant.id)},
        headers=customer_auth,
    )

    assert response.status_code == 422

    await place_order(customer_auth, address["id"])
    listing = await client.get(ORDERS, headers=customer_auth)
    assert listing.json()["meta"]["total_items"] == 1


async def test_an_anonymous_caller_cannot_reach_orders(client, tenant):
    assert (await client.get(ORDERS)).status_code == 401
    assert (await client.post(CHECKOUT, json={"address_id": str(tenant.id)})).status_code == 401
    assert (await client.post(f"{CHECKOUT}/preview")).status_code == 401
