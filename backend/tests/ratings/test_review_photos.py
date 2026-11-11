"""Customers uploading photos to their own reviews."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from tests.ratings.conftest import REVIEWS


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 30, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _clean_uploads():
    yield
    root = Path(get_settings().storage_local_path)
    for path in root.rglob("*"):
        if path.is_file():
            path.unlink()


async def _upload(client, review_id, headers, data=None, content_type="image/png"):
    return await client.post(
        f"{REVIEWS}/{review_id}/images/upload",
        files={"file": ("look.png", data if data is not None else _png(), content_type)},
        data={"alt_text": "Wearing it"},
        headers=headers,
    )


async def test_the_author_uploads_a_photo(client, buyer_auth, review):
    response = await _upload(client, review["id"], buyer_auth)

    images = response.json()["data"]["images"]
    assert response.status_code == 201
    assert len(images) == 1
    assert images[0]["image_url"].startswith(get_settings().storage_public_base_url)
    assert images[0]["alt_text"] == "Wearing it"


async def test_the_photo_shows_on_the_public_review_list(client, buyer_auth, review):
    await _upload(client, review["id"], buyer_auth)

    listed = await client.get(f"{REVIEWS}/product/{review['product_id']}")

    assert len(listed.json()["data"][0]["images"]) == 1


async def test_someone_else_cannot_add_photos(client, second_buyer_auth, review):
    response = await _upload(client, review["id"], second_buyer_auth)

    assert response.status_code == 403


async def test_only_images_are_accepted(client, buyer_auth, review):
    response = await _upload(client, review["id"], buyer_auth, b"%PDF-1.4", "application/pdf")

    assert response.status_code == 400


async def test_an_oversized_photo_is_refused(client, buyer_auth, review, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 100, raising=False)

    response = await _upload(client, review["id"], buyer_auth)

    assert response.status_code == 400, response.text
    assert "MB or smaller" in response.json()["message"]
    listed = await client.get(f"{REVIEWS}/product/{review['product_id']}")
    assert listed.json()["data"][0]["images"] == []


async def test_a_review_has_at_most_five_photos(client, buyer_auth, review):
    for _ in range(5):
        assert (await _upload(client, review["id"], buyer_auth)).status_code == 201

    response = await _upload(client, review["id"], buyer_auth)

    assert response.status_code == 400


async def test_the_author_removes_a_photo(client, buyer_auth, review):
    uploaded = (await _upload(client, review["id"], buyer_auth)).json()["data"]

    response = await client.delete(
        f"{REVIEWS}/{review['id']}/images/{uploaded['images'][0]['id']}", headers=buyer_auth
    )

    assert response.status_code == 200
    assert response.json()["data"]["images"] == []


async def test_uploading_needs_a_signed_in_customer(client, review):
    response = await _upload(client, review["id"], {})

    assert response.status_code == 401


async def test_editing_and_deleting_a_review_still_work(client, buyer_auth, review):
    edited = await client.patch(f"{REVIEWS}/{review['id']}", json={"rating": 3}, headers=buyer_auth)
    deleted = await client.delete(f"{REVIEWS}/{review['id']}", headers=buyer_auth)

    assert edited.json()["data"]["rating"] == 3
    assert deleted.status_code == 204
