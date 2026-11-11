from __future__ import annotations

from tests.ratings.conftest import ADMIN_REVIEWS, REVIEWS


async def test_admin_can_hide_a_review_from_the_storefront(
    client, admin_headers, reviewable_product, review
):
    response = await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_approved"] is False

    product_id = reviewable_product["product"]["id"]
    listed = await client.get(f"{REVIEWS}/product/{product_id}")
    assert listed.json()["data"] == []

    summary = await client.get(f"{REVIEWS}/product/{product_id}/summary")
    assert summary.json()["data"]["total_reviews"] == 0


async def test_admin_can_restore_a_hidden_review(
    client, admin_headers, reviewable_product, review
):
    await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )
    restored = await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": True},
        headers=admin_headers,
    )

    assert restored.status_code == 200, restored.text

    product_id = reviewable_product["product"]["id"]
    listed = await client.get(f"{REVIEWS}/product/{product_id}")
    assert len(listed.json()["data"]) == 1


async def test_moderation_list_can_filter_by_approval(client, admin_headers, review):
    await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )

    hidden = await client.get(
        ADMIN_REVIEWS, params={"is_approved": False}, headers=admin_headers
    )
    assert hidden.status_code == 200, hidden.text
    assert [item["id"] for item in hidden.json()["data"]] == [review["id"]]

    approved = await client.get(
        ADMIN_REVIEWS, params={"is_approved": True}, headers=admin_headers
    )
    assert approved.json()["data"] == []


async def test_moderation_list_carries_page_meta(client, admin_headers, review):
    response = await client.get(ADMIN_REVIEWS, headers=admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["meta"]["total_items"] == 1


async def test_moderation_list_is_scoped_to_the_tenant(
    other_client, other_admin_headers, review
):
    response = await other_client.get(ADMIN_REVIEWS, headers=other_admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []


async def test_moderators_still_see_a_hidden_review_on_the_product(
    client, admin_headers, reviewable_product, review
):
    product_id = reviewable_product["product"]["id"]
    await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )

    storefront = await client.get(f"{REVIEWS}/product/{product_id}")
    assert storefront.json()["data"] == []

    moderation = await client.get(
        f"{ADMIN_REVIEWS}/product/{product_id}", headers=admin_headers
    )
    assert moderation.status_code == 200, moderation.text
    assert [item["id"] for item in moderation.json()["data"]] == [review["id"]]
    assert moderation.json()["meta"]["total_items"] == 1


async def test_moderation_summary_counts_hidden_reviews(
    client, admin_headers, reviewable_product, review
):
    product_id = reviewable_product["product"]["id"]
    await client.patch(
        f"{ADMIN_REVIEWS}/{review['id']}",
        json={"is_approved": False},
        headers=admin_headers,
    )

    storefront = await client.get(f"{REVIEWS}/product/{product_id}/summary")
    assert storefront.json()["data"]["total_reviews"] == 0

    moderation = await client.get(
        f"{ADMIN_REVIEWS}/product/{product_id}/summary", headers=admin_headers
    )
    assert moderation.status_code == 200, moderation.text
    body = moderation.json()["data"]
    assert body["total_reviews"] == 1
    assert body["average_rating"] == 4.0


async def test_per_product_moderation_views_need_staff(
    client, customer_headers, reviewable_product, review
):
    product_id = reviewable_product["product"]["id"]

    listed = await client.get(
        f"{ADMIN_REVIEWS}/product/{product_id}", headers=customer_headers
    )
    assert listed.status_code == 403

    summary = await client.get(
        f"{ADMIN_REVIEWS}/product/{product_id}/summary", headers=customer_headers
    )
    assert summary.status_code == 403


async def test_per_product_moderation_is_scoped_to_the_tenant(
    other_client, other_admin_headers, reviewable_product, review
):
    product_id = reviewable_product["product"]["id"]

    response = await other_client.get(
        f"{ADMIN_REVIEWS}/product/{product_id}", headers=other_admin_headers
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"] == []
