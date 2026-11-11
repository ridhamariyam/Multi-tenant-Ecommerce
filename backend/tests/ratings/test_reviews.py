from __future__ import annotations

from uuid import uuid4

from app.orders.constants import OrderStatus
from tests.ratings.conftest import (
    ADMIN_REVIEWS,
    REVIEWS,
    make_sellable_product,
    place_order,
    review_payload,
)


async def test_a_delivered_purchase_can_be_reviewed(
    client, buyer_auth, reviewable_product, delivered_order
):
    """The whole point of the module: a shopper who received the goods may rate them."""
    response = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"]),
        headers=buyer_auth,
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["success"] is True

    created = body["data"]
    assert created["rating"] == 4
    assert created["is_verified_purchase"] is True
    assert created["is_approved"] is True
    assert created["product_id"] == reviewable_product["product"]["id"]
    assert created["order_id"] == str(delivered_order.id)


async def test_review_without_a_delivered_order_is_refused(
    client, non_buyer_auth, reviewable_product
):
    response = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"]),
        headers=non_buyer_auth,
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "PERMISSION_DENIED"


async def test_review_before_delivery_is_refused(
    client, session, tenant, admin_headers, non_buyer, non_buyer_auth
):
    listing = await make_sellable_product(client, admin_headers, "Linen Shirt")
    await place_order(session, tenant, non_buyer, listing, OrderStatus.SHIPPED.value)

    response = await client.post(
        REVIEWS, json=review_payload(listing["product"]["id"]), headers=non_buyer_auth
    )

    assert response.status_code == 403


async def test_reviewing_the_same_product_twice_conflicts(
    client, buyer_auth, reviewable_product, review
):
    """A duplicate is a 409, never a unique-violation 500."""
    response = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"], rating=1),
        headers=buyer_auth,
    )

    assert response.status_code == 409, response.text
    assert response.json()["error"]["code"] == "CONFLICT"


async def test_a_hidden_review_still_blocks_a_second_one(
    client, admin_headers, buyer_auth, reviewable_product, review
):
    hidden = await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )
    assert hidden.status_code == 200, hidden.text

    response = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"]),
        headers=buyer_auth,
    )
    assert response.status_code == 409, response.text


async def test_images_are_stored_with_the_review(
    client, session, tenant, admin_headers, second_buyer, second_buyer_auth
):
    listing = await make_sellable_product(client, admin_headers, "Canvas Tote")
    await place_order(
        session, tenant, second_buyer, listing, OrderStatus.DELIVERED.value
    )

    response = await client.post(
        REVIEWS,
        json=review_payload(
            listing["product"]["id"],
            images=[{"image_url": "https://cdn.test/tote.jpg", "alt_text": "In use"}],
        ),
        headers=second_buyer_auth,
    )

    assert response.status_code == 201, response.text
    images = response.json()["data"]["images"]
    assert len(images) == 1
    assert images[0]["image_url"] == "https://cdn.test/tote.jpg"
    assert images[0]["alt_text"] == "In use"


async def test_author_can_edit_their_review(client, buyer_auth, review):
    response = await client.patch(
        f"{REVIEWS}/{review['id']}",
        json={"rating": 2, "comment": "Shrank in the wash."},
        headers=buyer_auth,
    )

    assert response.status_code == 200, response.text
    updated = response.json()["data"]
    assert updated["rating"] == 2
    assert updated["comment"] == "Shrank in the wash."
    assert updated["title"] == review["title"]


async def test_editing_a_review_that_does_not_exist_is_a_404(client, buyer_auth):
    response = await client.patch(
        f"{REVIEWS}/{uuid4()}", json={"rating": 3}, headers=buyer_auth
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "NOT_FOUND"


async def test_author_can_delete_their_review(
    client, session, tenant, admin_headers, non_buyer, non_buyer_auth
):
    listing = await make_sellable_product(client, admin_headers, "Wool Scarf")
    await place_order(session, tenant, non_buyer, listing, OrderStatus.DELIVERED.value)

    created = await client.post(
        REVIEWS, json=review_payload(listing["product"]["id"]), headers=non_buyer_auth
    )
    assert created.status_code == 201, created.text
    review_id = created.json()["data"]["id"]

    deleted = await client.delete(f"{REVIEWS}/{review_id}", headers=non_buyer_auth)
    assert deleted.status_code == 204

    listed = await client.get(f"{REVIEWS}/product/{listing['product']['id']}")
    assert listed.json()["data"] == []


async def test_product_reviews_carry_page_meta(client, reviewable_product, review):
    response = await client.get(
        f"{REVIEWS}/product/{reviewable_product['product']['id']}",
        params={"page": 1, "page_size": 5},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["page"] == 1
    assert body["meta"]["page_size"] == 5
    assert body["meta"]["total_items"] == 1
    assert body["meta"]["total_pages"] == 1


async def test_rating_summary_averages_approved_reviews(
    client, buyer_auth, second_buyer_auth, reviewable_product, review, second_delivered_order
):
    second = await client.post(
        REVIEWS,
        json=review_payload(reviewable_product["product"]["id"], rating=2),
        headers=second_buyer_auth,
    )
    assert second.status_code == 201, second.text

    response = await client.get(
        f"{REVIEWS}/product/{reviewable_product['product']['id']}/summary"
    )

    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["total_reviews"] == 2
    assert summary["average_rating"] == 3.0
    assert summary["rating_distribution"] == {"1": 0, "2": 1, "3": 0, "4": 1, "5": 0}


async def test_summary_of_an_unreviewed_product_is_empty(client, reviewable_product):
    response = await client.get(f"{REVIEWS}/product/{uuid4()}/summary")

    assert response.status_code == 200, response.text
    summary = response.json()["data"]
    assert summary["total_reviews"] == 0
    assert summary["average_rating"] == 0.0
    assert summary["rating_distribution"] == {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
