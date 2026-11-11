"""Cart: viewing, adding, updating, removing and clearing."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.cart.models import CartItem
from app.cart.schemas import CartItemCreate
from app.cart.service import CartService
from app.catalogue.serializers import sellable_quantity
from app.catalogue.service import InventoryService
from tests.cart.conftest import CART, CUSTOMERS
from tests.catalogue.factories import PRODUCTS, VARIANTS
from tests.conftest import headers_for
from tests.helpers import run_concurrently


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", CART), ("post", f"{CART}/items"), ("delete", CART)],
)
async def test_the_cart_needs_authentication(client, tenant, method, path):
    response = await getattr(client, method)(path)

    assert response.status_code == 401


async def test_staff_cannot_use_the_customer_cart(client, staff_headers):
    response = await client.get(CART, headers=staff_headers)

    assert response.status_code == 403


async def test_an_empty_cart_is_created_on_first_view(client, customer_auth):
    response = await client.get(CART, headers=customer_auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["subtotal"] == "0.00"
    assert body["item_count"] == 0


async def test_the_same_cart_is_returned_every_time(client, customer_auth):
    first = await client.get(CART, headers=customer_auth)
    second = await client.get(CART, headers=customer_auth)

    assert first.json()["data"]["id"] == second.json()["data"]["id"]


async def test_a_variant_can_be_added(add_to_cart, customer_auth, variant):
    response = await add_to_cart(customer_auth, variant["id"], 2)

    assert response.status_code == 201
    item = response.json()["data"]["items"][0]
    assert item["variant_id"] == variant["id"]
    assert item["quantity"] == 2


async def test_an_added_item_carries_its_catalogue_details(
    add_to_cart, customer_auth, variant
):
    response = await add_to_cart(customer_auth, variant["id"], 1)

    item = response.json()["data"]["items"][0]
    assert item["product_name"]
    assert item["variant_name"] == variant["name"]
    assert item["sku"] == variant["sku"]
    assert item["image"]["url"]


async def test_adding_the_same_variant_twice_increases_the_quantity(
    add_to_cart, customer_auth, variant
):
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await add_to_cart(customer_auth, variant["id"], 3)

    body = response.json()["data"]
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 5


async def test_quantity_can_be_updated(client, add_to_cart, customer_auth, variant):
    added = await add_to_cart(customer_auth, variant["id"], 1)
    item_id = added.json()["data"]["items"][0]["id"]

    response = await client.patch(
        f"{CART}/items/{item_id}", json={"quantity": 4}, headers=customer_auth
    )

    assert response.status_code == 200
    assert response.json()["data"]["items"][0]["quantity"] == 4


async def test_an_item_can_be_removed(client, add_to_cart, customer_auth, variant):
    added = await add_to_cart(customer_auth, variant["id"], 1)
    item_id = added.json()["data"]["items"][0]["id"]

    response = await client.delete(f"{CART}/items/{item_id}", headers=customer_auth)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


async def test_clearing_empties_the_cart_but_keeps_it(
    client, add_to_cart, customer_auth, variant
):
    added = await add_to_cart(customer_auth, variant["id"], 2)
    cart_id = added.json()["data"]["id"]

    response = await client.delete(CART, headers=customer_auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["id"] == cart_id


@pytest.mark.parametrize("quantity", [0, -1, -50])
async def test_quantity_must_be_at_least_one(
    add_to_cart, customer_auth, variant, quantity
):
    response = await add_to_cart(customer_auth, variant["id"], quantity)

    assert response.status_code == 422


async def test_an_unknown_variant_is_rejected(add_to_cart, customer_auth):
    response = await add_to_cart(customer_auth, str(uuid4()), 1)

    assert response.status_code == 404
    assert response.json()["message"] == "Product variant not found"


async def test_an_inactive_variant_is_rejected(
    add_to_cart, customer_auth, new_variant
):
    variant = await new_variant(status="DRAFT")

    response = await add_to_cart(customer_auth, variant["id"], 1)

    assert response.status_code == 409
    assert response.json()["message"] == "Product variant is not available"


async def test_a_variant_of_an_archived_product_is_rejected(
    client, admin_headers, add_to_cart, customer_auth, variant
):
    await client.delete(f"{PRODUCTS}/{variant['product_id']}", headers=admin_headers)

    response = await add_to_cart(customer_auth, variant["id"], 1)

    assert response.status_code == 409


async def test_insufficient_stock_reports_what_is_available(
    add_to_cart, customer_auth, new_variant
):
    variant = await new_variant(initial_quantity=3)

    response = await add_to_cart(customer_auth, variant["id"], 5)

    assert response.status_code == 409
    assert response.json()["message"] == "Only 3 items are available"


async def test_stock_is_checked_against_the_combined_quantity(
    add_to_cart, customer_auth, new_variant
):
    """Two adds of 3 against 5 in stock must fail: the cart would hold 6."""
    variant = await new_variant(initial_quantity=5)
    await add_to_cart(customer_auth, variant["id"], 3)

    response = await add_to_cart(customer_auth, variant["id"], 3)

    assert response.status_code == 409


async def test_updating_beyond_stock_leaves_the_quantity_alone(
    client, add_to_cart, customer_auth, new_variant
):
    variant = await new_variant(initial_quantity=4)
    added = await add_to_cart(customer_auth, variant["id"], 1)
    item_id = added.json()["data"]["items"][0]["id"]

    response = await client.patch(
        f"{CART}/items/{item_id}", json={"quantity": 9}, headers=customer_auth
    )

    assert response.status_code == 409
    cart = await client.get(CART, headers=customer_auth)
    assert cart.json()["data"]["items"][0]["quantity"] == 1


async def test_another_customer_cannot_update_your_item(
    client, add_to_cart, customer_auth, variant, make_user, tenant
):
    added = await add_to_cart(customer_auth, variant["id"], 1)
    item_id = added.json()["data"]["items"][0]["id"]
    intruder = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["intruder"]))

    response = await client.patch(
        f"{CART}/items/{item_id}", json={"quantity": 5}, headers=intruder
    )

    assert response.status_code == 404


async def test_another_customer_cannot_delete_your_item(
    client, add_to_cart, customer_auth, variant, make_user, tenant
):
    added = await add_to_cart(customer_auth, variant["id"], 1)
    item_id = added.json()["data"]["items"][0]["id"]
    intruder = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["intruder"]))

    response = await client.delete(f"{CART}/items/{item_id}", headers=intruder)

    assert response.status_code == 404


async def test_another_tenants_customer_sees_their_own_empty_cart(
    other_client, add_to_cart, customer_auth, variant, make_user, other_tenant
):
    await add_to_cart(customer_auth, variant["id"], 2)
    theirs = headers_for(
        await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_b"])
    )

    response = await other_client.get(CART, headers=theirs)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


async def test_a_variant_from_another_tenant_cannot_be_added(
    other_client, variant, make_user, other_tenant
):
    theirs = headers_for(
        await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_a"])
    )

    response = await other_client.post(
        f"{CART}/items",
        json={"variant_id": variant["id"], "quantity": 1},
        headers=theirs,
    )

    assert response.status_code == 404


async def test_a_token_is_rejected_on_another_tenants_host(
    other_client, make_user, tenant, other_tenant
):
    mine = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["cross_host"]))

    response = await other_client.get(CART, headers=mine)

    assert response.status_code == 401


async def test_the_subtotal_uses_the_database_price(
    add_to_cart, customer_auth, variant
):
    response = await add_to_cart(customer_auth, variant["id"], 2)

    body = response.json()["data"]
    assert body["items"][0]["unit_price"] == variant["price"]
    assert body["subtotal"] == str(Decimal(variant["price"]) * 2)


async def test_a_price_sent_by_the_client_is_rejected(
    client, customer_auth, variant
):
    response = await client.post(
        f"{CART}/items",
        json={"variant_id": variant["id"], "quantity": 1, "unit_price": "1.00"},
        headers=customer_auth,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "unit_price"


async def test_a_price_change_shows_in_an_existing_cart(
    client, admin_headers, add_to_cart, customer_auth, variant
):
    """Nothing is copied into the cart, so the new price appears immediately."""
    await add_to_cart(customer_auth, variant["id"], 1)

    await client.patch(
        f"{VARIANTS}/{variant['id']}", json={"price": "1499.00"}, headers=admin_headers
    )

    response = await client.get(CART, headers=customer_auth)
    assert response.json()["data"]["items"][0]["unit_price"] == "1499.00"


async def test_adding_to_a_cart_does_not_reserve_stock(
    add_to_cart, customer_auth, variant, session, tenant
):
    await add_to_cart(customer_auth, variant["id"], 5)

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))

    assert item.reserved_quantity == 0
    assert sellable_quantity(item) == 10


async def test_two_customers_may_hold_the_same_stock(
    add_to_cart, variant, make_user, tenant
):
    first = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["shopper_one"]))
    second = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["shopper_two"]))

    await add_to_cart(first, variant["id"], 8)
    response = await add_to_cart(second, variant["id"], 8)

    assert response.status_code == 201


async def test_adding_the_same_variant_at_once_makes_one_line(
    engine, session, tenant, customer, variant
):
    """The unique constraint on (cart_id, variant_id) keeps this to one row."""

    async def add_one(db, _index):
        service = CartService(db, tenant.id, customer.id)
        return await service.add_item(
            CartItemCreate(variant_id=UUID(variant["id"]), quantity=1)
        )

    await run_concurrently(engine, 5, add_one)

    rows = await session.scalar(
        select(func.count())
        .select_from(CartItem)
        .where(
            CartItem.tenant_id == tenant.id,
            CartItem.variant_id == UUID(variant["id"]),
        )
    )
    assert rows == 1
