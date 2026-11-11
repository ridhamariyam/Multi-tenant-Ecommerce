"""Guest carts, merging into a customer cart, and the 30-day retention rule."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update

from app.cart.models import Cart, CartItem, CartStatus
from app.cart.repository import expire_stale_carts
from tests.cart.conftest import CART


def _token(cart: dict) -> dict[str, str]:
    return {"X-Cart-Token": cart["guest_token"]}


async def _guest(client) -> dict:
    response = await client.post(f"{CART}/guest")
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _age(session, cart_id, days: int) -> None:
    await session.execute(
        update(Cart)
        .where(Cart.id == UUID(cart_id))
        .values(last_activity_at=datetime.now(timezone.utc) - timedelta(days=days))
    )
    await session.commit()


async def test_a_guest_gets_a_cart_and_a_token(client, tenant):
    cart = await _guest(client)

    assert cart["guest_token"]
    assert cart["items"] == []
    assert cart["expires_at"] is not None


async def test_a_guest_adds_and_reads_items_with_the_token(client, tenant, variant, add_to_cart):
    cart = await _guest(client)

    added = await add_to_cart(_token(cart), variant["id"], 2)
    read = await client.get(CART, headers=_token(cart))

    assert added.status_code == 201
    assert read.json()["data"]["item_count"] == 2
    assert read.json()["data"]["guest_token"] is None


async def test_an_unknown_cart_token_is_404(client, tenant):
    response = await client.get(CART, headers={"X-Cart-Token": "not-a-real-token"})

    assert response.status_code == 404


async def test_a_guest_cart_is_scoped_to_its_tenant(client, other_client, tenant, other_tenant):
    cart = await _guest(client)

    response = await other_client.get(CART, headers=_token(cart))

    assert response.status_code == 404


async def test_only_the_token_hash_is_stored(client, session, tenant):
    cart = await _guest(client)

    stored = await session.scalar(select(Cart).where(Cart.id == UUID(cart["id"])))

    assert stored.guest_token_hash != cart["guest_token"]
    assert len(stored.guest_token_hash) == 64
    assert stored.customer_id is None


async def test_a_signed_in_customer_ignores_a_cart_token(
    client, tenant, customer_auth, variant, add_to_cart
):
    guest = await _guest(client)
    await add_to_cart(_token(guest), variant["id"], 1)

    response = await client.get(CART, headers={**customer_auth, **_token(guest)})

    assert response.json()["data"]["items"] == []


async def test_merging_moves_guest_items_into_the_customer_cart(
    client, tenant, customer_auth, new_variant, add_to_cart
):
    shared = await new_variant()
    only_guest = await new_variant()
    guest = await _guest(client)
    await add_to_cart(_token(guest), shared["id"], 2)
    await add_to_cart(_token(guest), only_guest["id"], 1)
    await add_to_cart(customer_auth, shared["id"], 1)

    response = await client.post(f"{CART}/merge", headers={**customer_auth, **_token(guest)})

    lines = {item["variant_id"]: item["quantity"] for item in response.json()["data"]["items"]}
    assert response.status_code == 200
    assert lines == {shared["id"]: 3, only_guest["id"]: 1}
    gone = await client.get(CART, headers=_token(guest))
    assert gone.status_code == 404


async def test_merging_caps_quantities_at_stock(
    client, tenant, customer_auth, new_variant, add_to_cart
):
    scarce = await new_variant(initial_quantity=3)
    guest = await _guest(client)
    await add_to_cart(_token(guest), scarce["id"], 2)
    await add_to_cart(customer_auth, scarce["id"], 2)

    response = await client.post(f"{CART}/merge", headers={**customer_auth, **_token(guest)})

    assert response.json()["data"]["items"][0]["quantity"] == 3


async def test_merging_needs_a_signed_in_customer(client, tenant):
    guest = await _guest(client)

    response = await client.post(f"{CART}/merge", headers=_token(guest))

    assert response.status_code == 401


async def test_an_idle_customer_cart_expires_after_30_days(
    client, session, tenant, customer_auth, variant, add_to_cart
):
    first = (await add_to_cart(customer_auth, variant["id"], 1)).json()["data"]
    await _age(session, first["id"], 31)

    response = await client.get(CART, headers=customer_auth)

    body = response.json()["data"]
    assert body["items"] == []
    assert body["id"] != first["id"]
    old = await session.scalar(select(Cart).where(Cart.id == UUID(first["id"])))
    await session.refresh(old)
    assert old.status == CartStatus.EXPIRED.value


async def test_a_29_day_old_cart_is_still_there(
    client, session, tenant, customer_auth, variant, add_to_cart
):
    cart = (await add_to_cart(customer_auth, variant["id"], 1)).json()["data"]
    await _age(session, cart["id"], 29)

    response = await client.get(CART, headers=customer_auth)

    assert response.json()["data"]["id"] == cart["id"]
    assert response.json()["data"]["item_count"] == 1


async def test_an_idle_guest_cart_expires(client, session, tenant, variant, add_to_cart):
    guest = await _guest(client)
    await add_to_cart(_token(guest), variant["id"], 1)
    await _age(session, guest["id"], 31)

    response = await client.get(CART, headers=_token(guest))

    assert response.status_code == 404


async def test_changing_the_cart_restarts_the_clock(
    client, session, tenant, customer_auth, variant, add_to_cart
):
    cart = (await add_to_cart(customer_auth, variant["id"], 1)).json()["data"]
    await _age(session, cart["id"], 20)

    await add_to_cart(customer_auth, variant["id"], 1)

    stored = await session.scalar(select(Cart).where(Cart.id == UUID(cart["id"])))
    await session.refresh(stored)
    assert stored.last_activity_at > datetime.now(timezone.utc) - timedelta(minutes=5)


async def test_the_expiry_job_empties_stale_carts(
    client, session, tenant, customer_auth, variant, add_to_cart
):
    stale = (await add_to_cart(customer_auth, variant["id"], 1)).json()["data"]
    fresh_guest = await _guest(client)
    await _age(session, stale["id"], 45)

    expired = await expire_stale_carts(session, datetime.now(timezone.utc) - timedelta(days=30))
    await session.commit()

    assert expired == 1
    items = await session.scalars(select(CartItem).where(CartItem.cart_id == UUID(stale["id"])))
    assert items.all() == []
    still = await session.scalar(select(Cart).where(Cart.id == UUID(fresh_guest["id"])))
    await session.refresh(still)
    assert still.status == CartStatus.ACTIVE.value
