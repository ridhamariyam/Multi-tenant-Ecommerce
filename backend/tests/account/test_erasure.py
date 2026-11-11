"""Deleting an account: the person goes, the trade record stays."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select

from app.addresses.models import Address
from app.auth.constants import AuthProvider, UserStatus
from app.cart.models import Cart, CartItem
from app.orders.models import Order
from app.ratings.models import Review
from app.search_filter.models import SearchHistory
from app.users.models import User, UserIdentity
from app.wishlist.models import Wishlist, WishlistItem
from tests.account.conftest import CHECKOUT, ME


async def _count(session, model, **filters) -> int:
    stmt = select(func.count()).select_from(model)
    for column, value in filters.items():
        stmt = stmt.where(getattr(model, column) == value)
    return int(await session.scalar(stmt) or 0)


async def test_erasing_an_account_anonymises_the_user(
    client, session, shopper, shopper_auth
):
    response = await client.delete(ME, headers=shopper_auth)
    assert response.status_code == 204, response.text

    stored = await session.get(User, shopper.id)
    assert stored is not None
    assert stored.status == UserStatus.DELETED.value
    assert stored.email is None
    assert stored.name is None
    assert stored.is_verified is False
    assert stored.phone is None


async def test_erasing_an_account_removes_authentication_identities(
    client, session, tenant, shopper, shopper_auth
):
    session.add_all(
        [
            UserIdentity(
                tenant_id=tenant.id,
                user_id=shopper.id,
                provider=AuthProvider.GOOGLE.value,
                subject="erasure-google-sub",
            ),
            UserIdentity(
                tenant_id=tenant.id,
                user_id=shopper.id,
                provider=AuthProvider.EMAIL.value,
                subject="erase@zeen.com",
            ),
        ]
    )
    await session.commit()

    response = await client.delete(ME, headers=shopper_auth)

    assert response.status_code == 204
    assert await session.scalar(
        select(UserIdentity.id).where(
            UserIdentity.tenant_id == tenant.id,
            UserIdentity.user_id == shopper.id,
        )
    ) is None


async def test_the_erased_token_stops_working(client, shopper_auth):
    assert (await client.get(ME, headers=shopper_auth)).status_code == 200

    await client.delete(ME, headers=shopper_auth)

    assert (await client.get(ME, headers=shopper_auth)).status_code == 401


async def test_shopping_data_is_deleted(
    client, session, shopper, shopper_auth, stocked_account
):
    assert await _count(session, Cart, customer_id=shopper.id) == 1
    assert await _count(session, Address, customer_id=shopper.id) == 1

    await client.delete(ME, headers=shopper_auth)

    assert await _count(session, Cart, customer_id=shopper.id) == 0
    assert await _count(session, CartItem) == 0
    assert await _count(session, Wishlist, customer_id=shopper.id) == 0
    assert await _count(session, WishlistItem) == 0
    assert await _count(session, Address, customer_id=shopper.id) == 0
    assert await _count(session, SearchHistory, user_id=shopper.id) == 0


async def test_orders_survive_because_tax_law_needs_them(
    client, session, shopper, shopper_auth, stocked_account
):
    placed = await client.post(
        CHECKOUT,
        json={"address_id": str(stocked_account["id"])},
        headers=shopper_auth,
    )
    assert placed.status_code == 201, placed.text
    order_id = placed.json()["data"]["id"]

    await client.delete(ME, headers=shopper_auth)

    order = await session.get(Order, order_id)
    assert order is not None
    assert order.customer_id == shopper.id
    assert order.total_amount > Decimal("0")
    assert order.delivery_name


async def test_reviews_stay_up_but_stop_naming_an_author(
    client, session, tenant, shopper, shopper_auth, variant
):
    review = Review(
        tenant_id=tenant.id,
        product_id=variant["product_id"],
        user_id=shopper.id,
        rating=5,
        comment="Still useful to the next shopper",
        is_verified_purchase=True,
        is_approved=True,
    )
    session.add(review)
    await session.commit()

    await client.delete(ME, headers=shopper_auth)

    stored = await session.get(Review, review.id)
    assert stored is not None
    assert stored.user_id is None
    assert stored.comment == "Still useful to the next shopper"


async def test_erasure_needs_authentication(client, tenant):
    assert (await client.delete(ME)).status_code == 401


async def test_the_freed_phone_number_can_be_used_again(
    client, session, shopper, shopper_auth, make_user, tenant
):
    """Anonymising releases the unique (tenant, phone) slot for a new signup."""
    phone = shopper.phone
    await client.delete(ME, headers=shopper_auth)

    replacement = await make_user(tenant=tenant, phone=phone)
    assert replacement.id != shopper.id
    assert replacement.phone == phone
