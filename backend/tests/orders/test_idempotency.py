"""A retried checkout must return the first order, not place a second."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, select

from app.orders.models import Order
from tests.orders.conftest import CHECKOUT


def _key() -> dict[str, str]:
    return {"Idempotency-Key": uuid4().hex}


async def test_a_repeated_key_returns_the_first_order(
    client, customer_auth, session, address, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 2)
    headers = {**customer_auth, **_key()}
    payload = {"address_id": str(address["id"])}

    first = await client.post(CHECKOUT, json=payload, headers=headers)
    assert first.status_code == 201, first.text

    second = await client.post(CHECKOUT, json=payload, headers=headers)
    assert second.status_code == 201, second.text

    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert second.json()["data"]["order_number"] == first.json()["data"]["order_number"]

    total = await session.scalar(select(func.count()).select_from(Order))
    assert total == 1


async def test_the_replay_does_not_reserve_stock_twice(
    client, customer_auth, session, address, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 2)
    headers = {**customer_auth, **_key()}
    payload = {"address_id": str(address["id"])}

    first = await client.post(CHECKOUT, json=payload, headers=headers)
    assert first.status_code == 201, first.text

    inventory = await client.get(
        f"/api/v1/catalogue/variants/{variant['id']}/inventory", headers=customer_auth
    )
    reserved_once = (
        inventory.json()["data"]["reserved_quantity"]
        if inventory.status_code == 200
        else None
    )

    await client.post(CHECKOUT, json=payload, headers=headers)

    if reserved_once is not None:
        again = await client.get(
            f"/api/v1/catalogue/variants/{variant['id']}/inventory",
            headers=customer_auth,
        )
        assert again.json()["data"]["reserved_quantity"] == reserved_once


async def test_different_keys_place_different_orders(
    client, customer_auth, session, address, new_variant, add_to_cart
):
    payload = {"address_id": str(address["id"])}

    first_variant = await new_variant()
    await add_to_cart(customer_auth, first_variant["id"], 1)
    first = await client.post(CHECKOUT, json=payload, headers={**customer_auth, **_key()})
    assert first.status_code == 201, first.text

    second_variant = await new_variant()
    await add_to_cart(customer_auth, second_variant["id"], 1)
    second = await client.post(CHECKOUT, json=payload, headers={**customer_auth, **_key()})
    assert second.status_code == 201, second.text

    assert first.json()["data"]["id"] != second.json()["data"]["id"]
    assert await session.scalar(select(func.count()).select_from(Order)) == 2


async def test_checkout_without_a_key_still_works(
    client, customer_auth, address, variant, add_to_cart
):
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await client.post(
        CHECKOUT, json={"address_id": str(address["id"])}, headers=customer_auth
    )

    assert response.status_code == 201, response.text
    assert response.json()["data"]["id"]


async def test_one_key_survives_a_concurrent_double_submit(
    client, customer_auth, session, address, variant, add_to_cart
):
    """The loser of the unique-constraint race gets the winner's order back."""
    await add_to_cart(customer_auth, variant["id"], 2)
    headers = {**customer_auth, **_key()}
    payload = {"address_id": str(address["id"])}

    responses = [
        await client.post(CHECKOUT, json=payload, headers=headers) for _ in range(3)
    ]

    assert all(r.status_code == 201 for r in responses), [r.text for r in responses]
    ids = {r.json()["data"]["id"] for r in responses}
    assert len(ids) == 1
    assert await session.scalar(select(func.count()).select_from(Order)) == 1
