"""Every response carries an X-Request-Id: the one the client sent, or a fresh one."""

from __future__ import annotations

from app.core.request_context import sanitize_request_id

CATEGORIES = "/api/v1/storefront/categories"
UNKNOWN = "/api/v1/does-not-exist"


async def test_a_request_without_the_header_still_gets_an_id(client, tenant):
    response = await client.get(CATEGORIES)

    assert response.status_code == 200
    request_id = response.headers["X-Request-Id"]
    assert sanitize_request_id(request_id) == request_id


async def test_the_id_the_client_sends_comes_back_unchanged(client, tenant):
    response = await client.get(CATEGORIES, headers={"X-Request-Id": "abc123"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == "abc123"


async def test_an_unusable_id_is_replaced_with_a_fresh_one(client, tenant):
    response = await client.get(CATEGORIES, headers={"X-Request-Id": "not a valid id!"})

    assert response.status_code == 200
    assert response.headers["X-Request-Id"] != "not a valid id!"


async def test_an_error_body_repeats_the_id_from_the_header(client):
    response = await client.get(UNKNOWN, headers={"X-Request-Id": "abc123"})

    assert response.status_code == 404
    assert response.headers["X-Request-Id"] == "abc123"
    assert response.json()["error"]["request_id"] == "abc123"
