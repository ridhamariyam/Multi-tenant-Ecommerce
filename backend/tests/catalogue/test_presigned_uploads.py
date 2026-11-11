"""Direct-to-storage image uploads (presigned POST), against a real MinIO.

scripts/test.sh starts a throwaway MinIO and passes TEST_S3_*; without it the
S3 tests skip. The local-disk behaviour is tested regardless.
"""

from __future__ import annotations

import io
import os
import uuid

import httpx
import pytest
from PIL import Image

from app.core.config import get_settings
from app.core.storage import S3Storage, pending_key, set_storage

PRESIGN = "/api/v1/catalogue/images/presign"
COMPLETE = "/api/v1/catalogue/images/complete"
UPLOAD = "/api/v1/catalogue/images/upload"


def product_complete(product_id) -> str:
    return f"/api/v1/catalogue/products/{product_id}/images/complete"


def _png(size=(40, 40)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (30, 75, 124)).save(buffer, format="PNG")
    return buffer.getvalue()


S3_ENDPOINT = os.environ.get("TEST_S3_ENDPOINT_URL")
needs_s3 = pytest.mark.skipif(not S3_ENDPOINT, reason="no test MinIO (run via scripts/test.sh)")


@pytest.fixture
def s3():
    """A fresh bucket per test, installed as the app's storage."""
    storage = S3Storage(
        bucket=f"cliq-test-{uuid.uuid4().hex[:12]}",
        region="us-east-1",
        access_key_id=os.environ["TEST_S3_ACCESS_KEY_ID"],
        secret_access_key=os.environ["TEST_S3_SECRET_ACCESS_KEY"],
        endpoint_url=S3_ENDPOINT,
        presign_endpoint_url=None,
        public_base_url=None,
        presign_expire_seconds=300,
    )
    set_storage(storage)
    yield storage
    set_storage(None)


@pytest.fixture
async def bucket(s3):
    await s3.ensure_bucket()
    return s3


async def _presign(client, headers, content_type="image/png", size=100):
    response = await client.post(
        PRESIGN, json={"content_type": content_type, "size_bytes": size}, headers=headers
    )
    return response


async def _browser_upload(ticket: dict, data: bytes, content_type: str = "image/png") -> httpx.Response:
    fields = dict(ticket["fields"])
    async with httpx.AsyncClient() as raw:
        return await raw.post(
            ticket["url"], data=fields, files={"file": ("photo", data, content_type)}
        )


# ------------------------------------------------------------- local backend


async def test_presign_is_refused_on_local_storage(client, admin_headers):
    set_storage(None)
    if get_settings().storage_backend != "local":
        pytest.skip("suite configured for s3")

    response = await _presign(client, admin_headers)

    assert response.status_code == 409
    assert "/catalogue/images/upload" in response.json()["message"]


async def test_presign_needs_catalogue_manage(client, staff_headers):
    response = await _presign(client, staff_headers)

    assert response.status_code == 403


async def test_presign_checks_the_declared_type_and_size(client, admin_headers):
    too_big = get_settings().max_upload_bytes + 1

    for payload in (
        {"content_type": "application/pdf", "size_bytes": 10},
        {"content_type": "image/svg+xml", "size_bytes": 10},
        {"content_type": "image/png", "size_bytes": too_big},
    ):
        response = await client.post(PRESIGN, json=payload, headers=admin_headers)
        assert response.status_code == 400, payload


# ------------------------------------------------------------------ S3 / MinIO


@needs_s3
async def test_full_direct_upload_publishes_a_public_image(client, admin_headers, bucket, tenant):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    uploaded = await _browser_upload(ticket, _png())
    completed = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)

    assert ticket["upload_id"].startswith(f"pending/{tenant.id}/")
    assert uploaded.status_code == 204, uploaded.text
    assert completed.status_code == 200, completed.text
    url = completed.json()["data"]["url"]
    assert url.startswith(f"{S3_ENDPOINT}/{bucket.bucket}/{tenant.id}/")
    assert url.endswith(".png")
    async with httpx.AsyncClient() as anonymous:
        public = await anonymous.get(url)
    assert public.status_code == 200
    assert public.headers["content-type"] == "image/png"
    assert public.content == _png()


@needs_s3
async def test_pending_uploads_are_not_publicly_readable(client, admin_headers, bucket):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, _png())

    async with httpx.AsyncClient() as anonymous:
        response = await anonymous.get(f"{S3_ENDPOINT}/{bucket.bucket}/{ticket['upload_id']}")

    assert response.status_code == 403


@needs_s3
async def test_the_policy_pins_content_type(client, admin_headers, bucket):
    ticket = (await _presign(client, admin_headers, content_type="image/png")).json()["data"]
    fields = dict(ticket["fields"], **{"Content-Type": "text/html"})

    async with httpx.AsyncClient() as raw:
        response = await raw.post(ticket["url"], data=fields, files={"file": ("x", b"<script>", "text/html")})

    assert response.status_code == 403


@needs_s3
async def test_the_policy_pins_the_key(client, admin_headers, bucket, other_tenant):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    fields = dict(ticket["fields"], key=f"{other_tenant.id}/takeover.png")

    async with httpx.AsyncClient() as raw:
        response = await raw.post(ticket["url"], data=fields, files={"file": ("x", _png(), "image/png")})

    assert response.status_code == 403


@needs_s3
async def test_the_policy_caps_the_size(client, admin_headers, bucket, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_bytes", 200)
    ticket = (await _presign(client, admin_headers, size=150)).json()["data"]

    response = await _browser_upload(ticket, _png((400, 400)) + b"\0" * 500)

    assert response.status_code == 400
    assert "EntityTooLarge" in response.text


@needs_s3
async def test_a_non_image_is_refused_on_completion_and_discarded(client, admin_headers, bucket):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, b"<html>not a png</html>")

    response = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)

    assert response.status_code == 400
    assert await bucket.read(ticket["upload_id"], max_bytes=10_000) is None


@needs_s3
async def test_completion_detects_the_real_format(client, admin_headers, bucket):
    """Declared PNG, actually JPEG: published as .jpg with the JPEG type."""
    buffer = io.BytesIO()
    Image.new("RGB", (30, 30)).save(buffer, format="JPEG")
    ticket = (await _presign(client, admin_headers, content_type="image/png")).json()["data"]
    await _browser_upload(ticket, buffer.getvalue())

    response = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)

    assert response.status_code == 200
    assert response.json()["data"]["url"].endswith(".jpg")


@needs_s3
async def test_an_upload_completes_once(client, admin_headers, bucket):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, _png())

    first = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)
    second = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)

    assert first.status_code == 200
    assert second.status_code == 404


@needs_s3
async def test_another_brand_cannot_complete_my_upload(client, admin_headers, other_client, other_admin_headers, bucket):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, _png())

    stolen = await other_client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=other_admin_headers)
    mine = await client.post(COMPLETE, json={"upload_id": ticket["upload_id"]}, headers=admin_headers)

    assert stolen.status_code == 404
    assert mine.status_code == 200


@needs_s3
async def test_malformed_upload_ids_are_not_found(client, admin_headers, bucket, tenant):
    for upload_id in (
        f"{tenant.id}/abc.png",
        f"pending/{tenant.id}/../../x",
        f"pending/{tenant.id}/{'g' * 32}",
        "pending/not-a-uuid/" + "a" * 32,
        pending_key(tenant.id),  # well-formed but never uploaded
    ):
        response = await client.post(COMPLETE, json={"upload_id": upload_id}, headers=admin_headers)
        assert response.status_code == 404, upload_id


@needs_s3
async def test_completing_onto_a_product_adds_the_image(client, admin_headers, bucket, product):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, _png())

    response = await client.post(
        product_complete(product["id"]),
        json={"upload_id": ticket["upload_id"], "alt_text": " Front ", "is_primary": True},
        headers=admin_headers,
    )

    assert response.status_code == 201, response.text
    image = response.json()["data"]
    assert image["alt_text"] == "Front"
    assert image["is_primary"] is True
    assert image["url"].startswith(f"{S3_ENDPOINT}/{bucket.bucket}/")


@needs_s3
async def test_an_unknown_product_leaves_the_upload_pending(client, admin_headers, bucket):
    ticket = (await _presign(client, admin_headers)).json()["data"]
    await _browser_upload(ticket, _png())

    response = await client.post(
        product_complete(uuid.uuid4()), json={"upload_id": ticket["upload_id"]}, headers=admin_headers
    )

    assert response.status_code == 404
    assert await bucket.read(ticket["upload_id"], max_bytes=10_000) is not None


@needs_s3
async def test_uploads_through_the_api_also_land_in_the_bucket(client, admin_headers, bucket, tenant):
    response = await client.post(UPLOAD, files={"file": ("k.png", _png(), "image/png")}, headers=admin_headers)

    assert response.status_code == 201
    assert response.json()["data"]["url"].startswith(f"{S3_ENDPOINT}/{bucket.bucket}/{tenant.id}/")


@needs_s3
async def test_storage_outage_is_reported_as_unavailable(client, admin_headers):
    set_storage(
        S3Storage(
            bucket="cliq-nowhere",
            region="us-east-1",
            access_key_id="x",
            secret_access_key="y",
            endpoint_url="http://127.0.0.1:1",
            presign_endpoint_url=None,
            public_base_url=None,
            presign_expire_seconds=300,
        )
    )
    try:
        response = await client.post(UPLOAD, files={"file": ("k.png", _png(), "image/png")}, headers=admin_headers)
    finally:
        set_storage(None)

    assert response.status_code == 503


@needs_s3
async def test_ensure_bucket_is_idempotent(s3):
    first = await s3.ensure_bucket()
    second = await s3.ensure_bucket()

    assert any("created" in step for step in first)
    assert not any("created" in step for step in second)
