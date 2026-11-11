"""Uploading photos while creating a product, before it has an id."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from tests.catalogue.factories import PRODUCTS

UPLOAD = "/api/v1/catalogue/images/upload"


def _png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (30, 75, 124)).save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _clean_uploads():
    yield
    root = Path(get_settings().storage_local_path)
    for path in root.rglob("*"):
        if path.is_file():
            path.unlink()


async def test_an_uploaded_photo_can_start_a_new_product(client, admin_headers, category):
    uploaded = await client.post(UPLOAD, files={"file": ("kurta.png", _png(), "image/png")}, headers=admin_headers)
    url = uploaded.json()["data"]["url"]

    created = await client.post(
        PRODUCTS,
        json={"category_id": category["id"], "name": "Photo First", "images": [{"url": url, "is_primary": True}]},
        headers=admin_headers,
    )

    assert uploaded.status_code == 201
    assert url.startswith(get_settings().storage_public_base_url + "/")
    assert created.status_code == 201, created.text
    assert created.json()["data"]["images"][0]["url"] == url


async def test_non_images_are_refused(client, admin_headers):
    response = await client.post(UPLOAD, files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")}, headers=admin_headers)

    assert response.status_code == 400


async def test_only_this_stores_upload_paths_are_accepted_as_relative_urls(client, admin_headers, category):
    base = get_settings().storage_public_base_url
    for url in (f"{base}/../etc/passwd", "/somewhere/else.png", "javascript:alert(1)", f"{base}/a.png?x=1"):
        response = await client.post(
            PRODUCTS,
            json={"category_id": category["id"], "name": "Bad", "images": [{"url": url}]},
            headers=admin_headers,
        )
        assert response.status_code == 422, url


async def test_uploading_needs_catalogue_manage(client, staff_headers):
    response = await client.post(UPLOAD, files={"file": ("k.png", _png(), "image/png")}, headers=staff_headers)

    assert response.status_code == 403
