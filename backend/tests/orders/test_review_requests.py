"""The automatic review request that follows a delivery."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update

from app.ratings.models import ReviewRequest

REVIEWS = "/api/v1/reviews"
ADMIN_REQUESTS = "/api/v1/admin/reviews/requests"


async def _deliver(order, set_status):
    for value in ("CONFIRMED", "PACKED", "SHIPPED", "DELIVERED"):
        await set_status(order["id"], value)


async def _make_due(session):
    await session.execute(
        update(ReviewRequest).values(send_after=datetime.now(timezone.utc) - timedelta(minutes=1))
    )
    await session.commit()


async def test_delivery_queues_a_review_request(client, admin_headers, order, set_status):
    await _deliver(order, set_status)

    listed = await client.get(ADMIN_REQUESTS, headers=admin_headers)

    requests = listed.json()["data"]
    assert len(requests) == 1
    assert requests[0]["order_id"] == order["id"]
    assert requests[0]["status"] == "PENDING"


async def test_no_request_before_delivery(client, admin_headers, order, set_status):
    await set_status(order["id"], "CONFIRMED")

    listed = await client.get(ADMIN_REQUESTS, headers=admin_headers)

    assert listed.json()["data"] == []


async def test_a_request_waits_for_its_delay(client, admin_headers, order, set_status):
    await _deliver(order, set_status)

    result = await client.post(f"{ADMIN_REQUESTS}/dispatch", headers=admin_headers)

    assert result.json()["data"] == {"sent": 0, "completed": 0}


async def test_due_requests_are_sent(client, session, admin_headers, order, set_status):
    await _deliver(order, set_status)
    await _make_due(session)

    result = await client.post(f"{ADMIN_REQUESTS}/dispatch", headers=admin_headers)
    listed = await client.get(ADMIN_REQUESTS, params={"status": "SENT"}, headers=admin_headers)

    assert result.json()["data"] == {"sent": 1, "completed": 0}
    assert listed.json()["data"][0]["sent_at"] is not None


async def test_the_customer_sees_what_to_review(client, customer_auth, order, set_status):
    await _deliver(order, set_status)

    response = await client.get(f"{REVIEWS}/pending", headers=customer_auth)

    pending = response.json()["data"]
    assert [p["order_number"] for p in pending] == [order["order_number"]]


async def test_reviewing_everything_completes_the_request(
    client, session, admin_headers, customer_auth, order, set_status
):
    await _deliver(order, set_status)
    product_id = order["items"][0]["product_id"]

    created = await client.post(
        REVIEWS, json={"product_id": product_id, "rating": 5}, headers=customer_auth
    )
    pending = await client.get(f"{REVIEWS}/pending", headers=customer_auth)
    request = await session.scalar(select(ReviewRequest))
    await session.refresh(request)

    assert created.status_code == 201
    assert pending.json()["data"] == []
    assert request.status == "COMPLETED"


async def test_a_reviewed_order_is_closed_not_sent(
    client, session, admin_headers, customer_auth, order, set_status
):
    await _deliver(order, set_status)
    await client.post(
        REVIEWS, json={"product_id": order["items"][0]["product_id"], "rating": 4},
        headers=customer_auth,
    )
    await _make_due(session)

    result = await client.post(f"{ADMIN_REQUESTS}/dispatch", headers=admin_headers)

    assert result.json()["data"]["sent"] == 0


async def test_dispatching_is_admin_only(client, staff_headers, tenant):
    response = await client.post(f"{ADMIN_REQUESTS}/dispatch", headers=staff_headers)

    assert response.status_code == 403


async def test_erasing_the_account_cancels_pending_requests(
    client, session, customer_auth, order, set_status
):
    await _deliver(order, set_status)

    await client.delete("/api/v1/auth/me", headers=customer_auth)

    request = await session.scalar(select(ReviewRequest))
    await session.refresh(request)
    assert request.status == "CANCELLED"
