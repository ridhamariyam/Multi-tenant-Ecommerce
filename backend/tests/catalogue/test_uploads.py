"""Uploading a product image: what's accepted, what's rejected, what's stored."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image

from app.core.config import get_settings
from tests.catalogue.factories import PRODUCTS


def _png(width: int = 40, height: int = 40) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (30, 75, 124)).save(buffer, format="PNG")
    return buffer.getvalue()


def upload_url(product_id) -> str:
    return f"{PRODUCTS}/{product_id}/images/upload"


@pytest.fixture(autouse=True)
def _clean_uploads():
    yield
    root = Path(get_settings().storage_local_path)
    for path in root.rglob("*"):
        if path.is_file():
            path.unlink()


async def test_an_uploaded_image_is_stored_and_attached(client, admin_headers, product):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("shoe.png", _png(), "image/png")},
        data={"alt_text": "Navy trainer", "is_primary": "true"},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    image = response.json()["data"]
    assert image["alt_text"] == "Navy trainer"
    assert image["is_primary"] is True
    assert image["url"].startswith(get_settings().storage_public_base_url)

    stored = Path(get_settings().storage_local_path) / image["url"].split("/media/")[-1]
    assert stored.is_file()
    assert stored.stat().st_size > 0


async def test_files_are_partitioned_by_tenant(client, admin_headers, product, tenant):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("shoe.png", _png(), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    assert str(tenant.id) in response.json()["data"]["url"]


async def test_a_pdf_pretending_to_be_an_image_is_refused(
    client, admin_headers, product
):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("invoice.pdf", b"%PDF-1.4 not an image", "application/pdf")},
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text
    assert "JPEG" in response.json()["message"]


async def test_a_declared_image_that_is_not_one_is_refused(
    client, admin_headers, product
):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("fake.png", b"this is not a PNG", "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text


async def test_an_oversized_upload_is_refused(client, admin_headers, product, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "max_upload_bytes", 100, raising=False)

    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("big.png", _png(600, 600), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text
    assert "MB or smaller" in response.json()["message"]


async def test_a_large_image_keeps_its_original_dimensions_and_bytes(
    client, admin_headers, product, monkeypatch
):
    settings = get_settings()
    monkeypatch.setattr(settings, "image_max_dimension", 100, raising=False)
    original = _png(400, 200)

    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("wide.png", original, "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    stored = (
        Path(settings.storage_local_path)
        / response.json()["data"]["url"].split("/media/")[-1]
    )
    with Image.open(stored) as saved:
        assert saved.size == (400, 200)
    assert stored.read_bytes() == original


async def test_uploading_requires_an_admin(client, customer_headers, product):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("shoe.png", _png(), "image/png")},
        headers=customer_headers,
    )

    assert response.status_code == 403


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40), (200, 10, 10)).save(buffer, format="JPEG")
    return buffer.getvalue()


def _png_carrying(text: str) -> bytes:
    """A valid PNG with `text` hidden in a metadata chunk, as polyglot attacks do."""
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Comment", text)
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buffer, format="PNG", pnginfo=info)
    return buffer.getvalue()


def _stored(url: str) -> Path:
    return Path(get_settings().storage_local_path) / url.split("/media/")[-1]


@pytest.mark.parametrize(
    "filename", ["page.html", "../../../etc/passwd.png", "x.svg", "shell.php", "no-extension"]
)
async def test_the_stored_name_never_comes_from_the_client(
    client, admin_headers, product, tenant, filename
):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": (filename, _png(), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    url = response.json()["data"]["url"]
    name = url.split("/")[-1]
    assert url == f"/media/{tenant.id}/{name}"
    assert len(name) == len("0" * 32 + ".png") and name.endswith(".png")
    assert _stored(url).resolve().is_relative_to(
        Path(get_settings().storage_local_path).resolve()
    )


async def test_the_extension_follows_the_content_not_the_declared_type(
    client, admin_headers, product
):
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("photo.png", _jpeg(), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    url = response.json()["data"]["url"]
    assert url.endswith(".jpg")
    with Image.open(_stored(url)) as saved:
        assert saved.format == "JPEG"


async def test_uploaded_image_metadata_and_bytes_are_preserved(client, admin_headers, product):
    original = _png_carrying("<script>alert(1)</script>")
    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("x.png", original, "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    assert _stored(response.json()["data"]["url"]).read_bytes() == original


async def test_an_allowed_type_wrapping_another_format_is_refused(
    client, admin_headers, product
):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buffer, format="GIF")

    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("anim.png", buffer.getvalue(), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text


async def test_an_image_with_too_many_pixels_is_refused_before_decoding(
    client, admin_headers, product, monkeypatch
):
    monkeypatch.setattr("app.catalogue.uploads.MAX_SOURCE_PIXELS", 100)

    response = await client.post(
        upload_url(product["id"]),
        files={"file": ("big.png", _png(40, 40), "image/png")},
        headers=admin_headers,
    )

    assert response.status_code == 400, response.text
    assert "pixels" in response.json()["message"]


async def test_served_media_cannot_be_sniffed_or_run(client, admin_headers, product):
    uploaded = await client.post(
        upload_url(product["id"]),
        files={"file": ("shoe.png", _png(), "image/png")},
        headers=admin_headers,
    )
    url = uploaded.json()["data"]["url"]

    response = await client.get(url)

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in response.headers["content-security-policy"]
