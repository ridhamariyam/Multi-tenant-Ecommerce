"""Inventory: stock levels, reservations and movement history."""

from __future__ import annotations

from uuid import UUID

import pytest

from app.catalogue.service import InventoryService
from app.core.exceptions import ConflictError
from tests.catalogue.factories import PRODUCTS, inventory_url
from tests.helpers import run_concurrently, succeeded


async def test_a_new_variant_starts_with_an_inventory_record(new_variant):
    variant = await new_variant(initial_quantity=7)

    assert variant["inventory"]["available_quantity"] == 7
    assert variant["inventory"]["reserved_quantity"] == 0
    assert variant["inventory"]["sellable_quantity"] == 7


async def test_stock_can_be_read(client, admin_headers, variant):
    response = await client.get(inventory_url(variant["id"]), headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["available_quantity"] == 10


async def test_stock_can_be_set_to_an_exact_quantity(client, admin_headers, variant):
    response = await client.put(
        inventory_url(variant["id"]),
        json={"available_quantity": 42},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["available_quantity"] == 42


async def test_stock_can_be_adjusted_up_and_down(client, admin_headers, variant):
    response = await client.post(
        inventory_url(variant["id"], "adjust"),
        json={"delta": 5, "reason": "RESTOCK"},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["available_quantity"] == 15


async def test_stock_cannot_be_driven_negative(client, admin_headers, variant):
    response = await client.post(
        inventory_url(variant["id"], "adjust"),
        json={"delta": -11},
        headers=admin_headers,
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "STOCK_BELOW_RESERVED"


async def test_a_refused_adjustment_leaves_stock_untouched(
    client, admin_headers, variant
):
    await client.post(
        inventory_url(variant["id"], "adjust"),
        json={"delta": -11},
        headers=admin_headers,
    )

    response = await client.get(inventory_url(variant["id"]), headers=admin_headers)

    assert response.json()["data"]["available_quantity"] == 10


async def test_stock_cannot_be_set_below_what_is_reserved(
    client, admin_headers, session, tenant, variant
):
    await InventoryService(session, tenant.id).reserve(UUID(variant["id"]), 3)

    response = await client.put(
        inventory_url(variant["id"]),
        json={"available_quantity": 1},
        headers=admin_headers,
    )

    assert response.status_code == 409


async def test_the_low_stock_threshold_can_be_configured(
    client, admin_headers, variant
):
    response = await client.put(
        inventory_url(variant["id"], "threshold"),
        json={"low_stock_threshold": 20},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["is_low_stock"] is True


async def test_reserving_stock_lowers_what_is_sellable(
    client, admin_headers, session, tenant, variant
):
    await InventoryService(session, tenant.id).reserve(UUID(variant["id"]), 4)

    response = await client.get(inventory_url(variant["id"]), headers=admin_headers)

    body = response.json()["data"]
    assert body["available_quantity"] == 10
    assert body["reserved_quantity"] == 4
    assert body["sellable_quantity"] == 6


async def test_reserving_more_than_exists_is_refused(session, tenant, new_variant):
    variant = await new_variant(initial_quantity=2)

    with pytest.raises(ConflictError) as error:
        await InventoryService(session, tenant.id).reserve(UUID(variant["id"]), 3)

    assert error.value.error_code == "INSUFFICIENT_STOCK"


async def test_releasing_a_reservation_gives_the_stock_back(
    client, admin_headers, session, tenant, variant
):
    service = InventoryService(session, tenant.id)
    await service.reserve(UUID(variant["id"]), 4)
    await service.release(UUID(variant["id"]), 4)

    response = await client.get(inventory_url(variant["id"]), headers=admin_headers)

    body = response.json()["data"]
    assert body["reserved_quantity"] == 0
    assert body["sellable_quantity"] == 10


async def test_fulfilling_an_order_removes_the_stock(
    client, admin_headers, session, tenant, variant
):
    service = InventoryService(session, tenant.id)
    await service.reserve(UUID(variant["id"]), 3)
    await service.fulfil(UUID(variant["id"]), 3)

    response = await client.get(inventory_url(variant["id"]), headers=admin_headers)

    body = response.json()["data"]
    assert body["available_quantity"] == 7
    assert body["reserved_quantity"] == 0


async def test_every_change_is_recorded_as_a_movement(client, admin_headers, variant):
    await client.post(
        inventory_url(variant["id"], "adjust"),
        json={"delta": 3, "reason": "RESTOCK"},
        headers=admin_headers,
    )

    response = await client.get(
        inventory_url(variant["id"], "movements"), headers=admin_headers
    )

    reasons = [movement["reason"] for movement in response.json()["data"]]
    assert "RESTOCK" in reasons
    assert "INITIAL" in reasons


async def test_another_tenants_inventory_is_not_found(
    other_client, other_admin_headers, variant
):
    response = await other_client.get(
        inventory_url(variant["id"]), headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_concurrent_reservations_never_oversell(engine, tenant, new_variant):
    """10 in stock, 8 requests wanting 2 each: exactly 5 may succeed."""
    variant = await new_variant(initial_quantity=10)

    async def reserve(db, _index):
        return await InventoryService(db, tenant.id).reserve(UUID(variant["id"]), 2)

    results = await run_concurrently(engine, 8, reserve)

    assert len(succeeded(results)) == 5


async def test_a_variant_can_carry_options(client, admin_headers, product):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={
            "sku": "TSH-BLK-M",
            "name": "M / Black",
            "price": "999.00",
            "options": [
                {"name": "Color", "value": "Black"},
                {"name": "Size", "value": "M"},
            ],
        },
        headers=admin_headers,
    )

    assert response.status_code == 201
    assert response.json()["data"]["options"] == {"Color": "Black", "Size": "M"}


async def test_an_option_name_cannot_repeat_in_one_variant(
    client, admin_headers, product
):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={
            "sku": "DUP-1",
            "name": "Duplicate",
            "price": "10.00",
            "options": [
                {"name": "Size", "value": "M"},
                {"name": "Size", "value": "L"},
            ],
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_variants_of_one_product_share_option_names(
    client, admin_headers, product, new_variant
):
    """Two variants naming "Color" reuse one option, they do not create two."""
    await new_variant(options=[{"name": "Color", "value": "Black"}])
    await new_variant(options=[{"name": "Color", "value": "Ivory"}])

    response = await client.get(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    options = response.json()["data"]["options"]
    assert [option["name"] for option in options] == ["Color"]
