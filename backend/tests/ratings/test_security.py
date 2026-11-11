from __future__ import annotations

from uuid import UUID, uuid4

from app.orders.constants import OrderStatus
from tests.ratings.conftest import (
    ADMIN_REVIEWS,
    REVIEWS,
    make_sellable_product,
    place_order,
    review_payload,
)


async def test_reviews_do_not_leak_across_tenants(
    client, tenant, other_tenant_listing, other_tenant_review
):
    """Zeen's storefront must not read Acme's reviews, product id or not."""
    product_id = other_tenant_listing["product"]["id"]

    response = await client.get(f"{REVIEWS}/product/{product_id}")

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


async def test_rating_summary_does_not_leak_across_tenants(
    client, tenant, other_tenant_listing, other_tenant_review
):
    product_id = other_tenant_listing["product"]["id"]

    response = await client.get(f"{REVIEWS}/product/{product_id}/summary")

    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["total_reviews"] == 0
    assert summary["average_rating"] == 0.0


async def test_another_tenants_review_cannot_be_edited(
    client, buyer_auth, other_tenant_review
):
    response = await client.patch(
        f"{REVIEWS}/{other_tenant_review.id}", json={"rating": 1}, headers=buyer_auth
    )

    assert response.status_code == 404


async def test_another_tenants_review_cannot_be_moderated(
    client, admin_headers, other_tenant_review
):
    response = await client.patch(
        f"{ADMIN_REVIEWS}/{other_tenant_review.id}",
        json={"is_approved": False},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_reviewing_another_tenants_product_is_refused(
    client, buyer_auth, other_tenant_listing
):
    response = await client.post(
        REVIEWS,
        json=review_payload(other_tenant_listing["product"]["id"]),
        headers=buyer_auth,
    )

    assert response.status_code == 403


async def test_author_cannot_approve_their_own_review(client, admin_headers, buyer_auth, review):
    """is_approved is a moderator's switch; the author's payload may not carry it."""
    hidden = await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )
    assert hidden.status_code == 200, hidden.text

    response = await client.patch(
        f"{REVIEWS}/{review['id']}",
        json={"rating": 5, "is_approved": True},
        headers=buyer_auth,
    )

    assert response.status_code == 422, response.text
    assert response.json()["error"]["details"][0]["field"] == "is_approved"

    # The rejected request changed nothing, approval included.
    listed = await client.get(ADMIN_REVIEWS, headers=admin_headers)
    stored = listed.json()["data"][0]
    assert stored["is_approved"] is False
    assert stored["rating"] == 4


async def test_creating_a_review_requires_authentication(client, reviewable_product):
    response = await client.post(
        REVIEWS, json=review_payload(reviewable_product["product"]["id"])
    )

    assert response.status_code == 401


async def test_moderation_requires_an_admin(client, buyer_auth, customer_headers, review):
    listed = await client.get(ADMIN_REVIEWS, headers=customer_headers)
    assert listed.status_code == 403

    moderated = await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=buyer_auth,
    )
    assert moderated.status_code == 403


async def test_editing_another_shoppers_review_is_refused(
    client, session, tenant, admin_headers, non_buyer, non_buyer_auth, review
):
    listing = await make_sellable_product(client, admin_headers, "Suede Boot")
    await place_order(session, tenant, non_buyer, listing, OrderStatus.DELIVERED.value)

    response = await client.patch(
        f"{REVIEWS}/{review['id']}", json={"rating": 1}, headers=non_buyer_auth
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_deleting_another_shoppers_review_is_refused(
    client, non_buyer_auth, review
):
    response = await client.delete(f"{REVIEWS}/{review['id']}", headers=non_buyer_auth)

    assert response.status_code == 403


async def test_deleting_a_review_that_does_not_exist_is_a_404(client, buyer_auth):
    response = await client.delete(f"{REVIEWS}/{uuid4()}", headers=buyer_auth)

    assert response.status_code == 404


def uuid_of(entity) -> UUID:
    """The id of a fixture that may be an ORM row or a response payload."""
    if isinstance(entity, dict):
        return UUID(entity["id"] if "id" in entity else entity["product"]["id"])
    return entity.id


async def test_a_review_outlives_the_product_and_the_account(
    session, tenant, buyer, reviewable_product, review
):
    """SET NULL must null only the column that pointed at the deleted row."""
    from sqlalchemy import delete, select

    from app.catalogue.models import Product
    from app.ratings.models import Review
    from app.users.models import User

    await session.execute(
        delete(Product).where(Product.id == uuid_of(reviewable_product))
    )
    await session.execute(delete(User).where(User.id == buyer.id))
    await session.commit()

    stored = await session.scalar(select(Review).where(Review.id == uuid_of(review)))
    assert stored is not None
    assert stored.tenant_id == tenant.id
    assert stored.product_id is None
    assert stored.user_id is None
    assert stored.rating == 4
