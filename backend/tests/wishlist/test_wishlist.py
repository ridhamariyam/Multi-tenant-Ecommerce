from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.catalogue.serializers import sellable_quantity
from app.catalogue.service import InventoryService
from app.wishlist.models import WishlistItem
from app.wishlist.schemas import WishListItemCreate
from app.wishlist.service import WishListService
from tests.catalogue.factories import PRODUCTS
from tests.conftest import headers_for
from tests.helpers import run_concurrently
from tests.wishlist.conftest import CUSTOMERS, WISHLIST


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", WISHLIST), ("post", f"{WISHLIST}/items"), ("delete", WISHLIST)],
)
async def test_the_wishlist_needs_authentication(client, tenant, method, path):
    response = await getattr(client, method)(path)

    assert response.status_code == 401


async def test_staff_cannot_use_the_customer_wishlist(client, staff_headers):
    response = await client.get(WISHLIST, headers=staff_headers)

    assert response.status_code == 403


async def test_an_empty_wishlist_is_created_on_first_view(client, customer_auth):
    response = await client.get(WISHLIST, headers=customer_auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []


async def test_the_same_wishlist_is_returned_every_time(client, customer_auth):
    first = await client.get(WISHLIST, headers=customer_auth)
    second = await client.get(WISHLIST, headers=customer_auth)

    assert first.json()["data"]["id"] == second.json()["data"]["id"]


async def test_a_variant_can_be_added(add_to_wishlist, customer_auth, variant):
    response = await add_to_wishlist(customer_auth, variant["id"])

    assert response.status_code == 201
    item = response.json()["data"]["items"][0]
    assert item["variant_id"] == variant["id"]


async def test_an_added_item_carries_its_catalogue_details(add_to_wishlist, customer_auth, variant):
    response = await add_to_wishlist(customer_auth, variant["id"])

    item = response.json()["data"]["items"][0]
    assert item["product_name"]
    assert item["variant_name"] == variant["name"]
    assert item["sku"] == variant["sku"]
    assert item["image"]["url"]


async def test_adding_the_same_variant_twice_is_rejected(add_to_wishlist, customer_auth, variant):
    await add_to_wishlist(customer_auth, variant["id"])

    response = await add_to_wishlist(customer_auth, variant["id"])

    assert response.status_code == 409
    assert response.json()["message"] == "Item already in wishlist"


async def test_an_item_can_be_removed(client, add_to_wishlist, customer_auth, variant):
    added = await add_to_wishlist(customer_auth, variant["id"])
    item_id = added.json()["data"]["items"][0]["id"]

    response = await client.delete(f"{WISHLIST}/items/{item_id}", headers=customer_auth)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


async def test_clearing_empties_the_wishlist_but_keeps_it(
    client, add_to_wishlist, customer_auth, variant
):
    added = await add_to_wishlist(customer_auth, variant["id"])
    wishlist_id = added.json()["data"]["id"]

    response = await client.delete(WISHLIST, headers=customer_auth)

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["items"] == []
    assert body["id"] == wishlist_id


async def test_an_unknown_variant_is_rejected(add_to_wishlist, customer_auth):
    response = await add_to_wishlist(customer_auth, str(uuid4()))

    assert response.status_code == 404
    assert response.json()["message"] == "Product variant not found"


async def test_an_inactive_variant_is_rejected(add_to_wishlist, customer_auth, new_variant):
    variant = await new_variant(status="DRAFT")

    response = await add_to_wishlist(customer_auth, variant["id"])

    assert response.status_code == 409
    assert response.json()["message"] == "Product variant is not available"


async def test_a_variant_of_an_archived_product_is_rejected(
    client, admin_headers, add_to_wishlist, customer_auth, variant
):
    await client.delete(f"{PRODUCTS}/{variant['product_id']}", headers=admin_headers)

    response = await add_to_wishlist(customer_auth, variant["id"])

    assert response.status_code == 409


async def test_different_variants_of_the_same_product_can_both_be_added(
    add_to_wishlist, customer_auth, variant, new_variant
):
    green_variant = await new_variant(product_id=variant["product_id"])

    await add_to_wishlist(customer_auth, variant["id"])

    response = await add_to_wishlist(customer_auth, green_variant["id"])

    assert response.status_code == 201
    items = response.json()["data"]["items"]
    assert len(items) == 2

    variant_ids = [item["variant_id"] for item in items]
    assert variant["id"] in variant_ids
    assert green_variant["id"] in variant_ids


async def test_another_customer_cannot_delete_your_item(
    client, add_to_wishlist, customer_auth, variant, make_user, tenant
):
    added = await add_to_wishlist(customer_auth, variant["id"])
    item_id = added.json()["data"]["items"][0]["id"]
    intruder = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["intruder"]))

    response = await client.delete(f"{WISHLIST}/items/{item_id}", headers=intruder)

    assert response.status_code == 404


async def test_another_tenants_customer_sees_their_own_empty_wishlist(
    other_client, add_to_wishlist, customer_auth, variant, make_user, other_tenant
):
    await add_to_wishlist(customer_auth, variant["id"])
    theirs = headers_for(await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_b"]))

    response = await other_client.get(WISHLIST, headers=theirs)

    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


async def test_a_variant_from_another_tenant_cannot_be_added(
    other_client, variant, make_user, other_tenant
):
    theirs = headers_for(await make_user(tenant=other_tenant, phone=CUSTOMERS["tenant_a"]))

    response = await other_client.post(
        f"{WISHLIST}/items",
        json={"variant_id": variant["id"]},
        headers=theirs,
    )

    assert response.status_code == 404


async def test_a_token_is_rejected_on_another_tenants_host(
    other_client, make_user, tenant, other_tenant
):
    mine = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["cross_host"]))

    response = await other_client.get(WISHLIST, headers=mine)

    assert response.status_code == 401


async def test_adding_to_a_wishlist_does_not_reserve_stock(
    add_to_wishlist, customer_auth, variant, session, tenant
):
    await add_to_wishlist(customer_auth, variant["id"])

    item = await InventoryService(session, tenant.id).get(UUID(variant["id"]))

    assert item.reserved_quantity == 0
    assert sellable_quantity(item) == 10


async def test_two_customers_may_hold_the_same_stock(add_to_wishlist, variant, make_user, tenant):
    first = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["shopper_one"]))
    second = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["shopper_two"]))

    await add_to_wishlist(first, variant["id"])
    response = await add_to_wishlist(second, variant["id"])

    assert response.status_code == 201


async def test_adding_the_same_variant_at_once_makes_one_line(
    engine, session, tenant, customer, variant
):
    async def add_one(db, _index):
        service = WishListService(db, tenant.id, customer.id)
        return await service.add_item(WishListItemCreate(variant_id=UUID(variant["id"])))

    await run_concurrently(engine, 5, add_one)

    rows = await session.scalar(
        select(func.count())
        .select_from(WishlistItem)
        .where(
            WishlistItem.tenant_id == tenant.id,
            WishlistItem.variant_id == UUID(variant["id"]),
        )
    )
    assert rows == 1
