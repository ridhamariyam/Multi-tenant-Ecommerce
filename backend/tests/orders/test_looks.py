"""Lookbooks: a cover uploaded to the store, products pinned on it, published."""

from __future__ import annotations

import io

from PIL import Image


LOOKS = "/api/v1/admin/looks"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 90), (200, 180, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _cover(client, admin_headers) -> str:
    response = await client.post(
        "/api/v1/catalogue/images/upload", files={"file": ("cover.png", _png(), "image/png")}, headers=admin_headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]["url"]


async def test_a_look_is_built_published_and_shown(client, admin_headers, variant):  # noqa: F811
    product_id = variant["product_id"]
    draft = await client.post(LOOKS, json={"title": "Monsoon edit"}, headers=admin_headers)
    look_id = draft.json()["data"]["id"]

    early = await client.post(f"{LOOKS}/{look_id}/publish", json={"published": True}, headers=admin_headers)
    saved = await client.put(
        f"{LOOKS}/{look_id}",
        json={"title": "Monsoon edit", "cover_url": await _cover(client, admin_headers), "pins": [{"product_id": product_id, "x": 0.5, "y": 0.3}]},
        headers=admin_headers,
    )
    published = await client.post(f"{LOOKS}/{look_id}/publish", json={"published": True}, headers=admin_headers)
    shown = (await client.get("/api/v1/storefront/looks")).json()["data"]

    assert draft.status_code == 201 and draft.json()["data"]["slug"] == "monsoon-edit"
    assert early.status_code == 409
    assert saved.status_code == 200, saved.text
    assert published.json()["data"]["status"] == "PUBLISHED"
    assert len(shown) == 1 and shown[0]["pins"][0]["x"] == 0.5 and shown[0]["cover_url"]


async def test_only_uploaded_images_and_own_products(client, admin_headers, variant):  # noqa: F811
    import uuid

    outside = await client.post(LOOKS, json={"title": "X", "cover_url": "https://evil.example/x.jpg"}, headers=admin_headers)
    foreign = await client.post(
        LOOKS, json={"title": "Y", "pins": [{"product_id": str(uuid.uuid4()), "x": 0.1, "y": 0.1}]}, headers=admin_headers
    )
    off_image = await client.post(
        LOOKS, json={"title": "Z", "pins": [{"product_id": variant["product_id"], "x": 1.5, "y": 0.1}]}, headers=admin_headers
    )

    assert outside.status_code == 400
    assert foreign.status_code == 400
    assert off_image.status_code == 422


async def test_drafts_are_not_on_the_store(client, admin_headers):
    await client.post(LOOKS, json={"title": "Hidden"}, headers=admin_headers)
    assert (await client.get("/api/v1/storefront/looks")).json()["data"] == []
