"""The shared character library: platform admins curate, brands browse."""

from __future__ import annotations

import io
import uuid

import pytest_asyncio
from PIL import Image

LIBRARY = "/api/v1/platform/virtual-models"
ADMIN = "/api/v1/platform/admin/virtual-models"


def _jpeg() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (60, 120), (200, 180, 160)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest_asyncio.fixture(loop_scope="session")
async def platform_admin(make_merchant):
    return await make_merchant("root@platform.example.com", platform_admin=True)


async def _create(platform, admin, **overrides) -> dict:
    body = {
        "name": f"Ava {uuid.uuid4().hex[:6]}",
        "gender_presentation": "FEMININE",
        "available_categories": ["Tops", "tops", " Dresses "],
        "supported_garments": ["tops", "one-pieces"],
        "license_note": "Licensed from Studio X, contract 42",
        **overrides,
    }
    response = await platform.post(LIBRARY, json=body, headers=admin.headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _photo(platform, admin, model_id, *, primary=True, label=None):
    data = {"primary": str(primary).lower()}
    if label:
        data["label"] = label
    return await platform.post(
        f"{ADMIN}/{model_id}/images",
        data=data,
        files={"file": ("ava.jpg", _jpeg(), "image/jpeg")},
        headers=admin.headers,
    )


async def _activate(platform, admin, model_id, active=True):
    return await platform.put(f"{LIBRARY}/{model_id}", json={"is_active": active}, headers=admin.headers)


async def test_admin_builds_a_character_and_brands_see_it_once_active(platform, platform_admin, brand_a):
    model = await _create(platform, platform_admin)
    assert model["is_active"] is False
    assert model["available_categories"] == ["tops", "dresses"]

    hidden = await platform.get(f"{LIBRARY}/{model['id']}", headers=brand_a.headers)
    no_photo = await _activate(platform, platform_admin, model["id"])
    photo = await _photo(platform, platform_admin, model["id"])
    active = await _activate(platform, platform_admin, model["id"])
    listed = await platform.get(LIBRARY, headers=brand_a.headers)
    one = await platform.get(f"{LIBRARY}/{model['id']}", headers=brand_a.headers)

    assert hidden.status_code == 404
    assert no_photo.status_code == 400
    assert no_photo.json()["error"]["code"] == "VIRTUAL_MODEL_NO_IMAGE"
    assert photo.status_code == 201 and photo.json()["data"]["image_url"]
    assert active.status_code == 200 and active.json()["data"]["is_active"] is True
    assert model["id"] in [m["id"] for m in listed.json()["data"]]
    assert one.status_code == 200
    assert "license_note" not in one.json()["data"]


async def test_deactivated_characters_disappear_for_brands(platform, platform_admin, brand_a):
    model = await _create(platform, platform_admin)
    await _photo(platform, platform_admin, model["id"])
    await _activate(platform, platform_admin, model["id"])
    await _activate(platform, platform_admin, model["id"], active=False)

    listed = await platform.get(LIBRARY, headers=brand_a.headers)
    admin_view = await platform.get(f"{ADMIN}/{model['id']}", headers=platform_admin.headers)

    assert model["id"] not in [m["id"] for m in listed.json()["data"]]
    assert admin_view.status_code == 200 and admin_view.json()["data"]["is_active"] is False


async def test_only_platform_admins_manage_the_library(platform, make_merchant, brand_a, platform_admin):
    plain = await make_merchant("plain@brands.example.com")
    model = await _create(platform, platform_admin)
    body = {"name": "X", "gender_presentation": "MASCULINE"}

    for headers in (brand_a.headers, plain.headers, {}):
        assert (await platform.post(LIBRARY, json=body, headers=headers)).status_code in (401, 403)
        assert (await platform.put(f"{LIBRARY}/{model['id']}", json={"name": "Y"}, headers=headers)).status_code in (401, 403)
        assert (await platform.get(ADMIN, headers=headers)).status_code in (401, 403)
        upload = await platform.post(
            f"{ADMIN}/{model['id']}/images", files={"file": ("a.jpg", _jpeg(), "image/jpeg")}, headers=headers
        )
        assert upload.status_code in (401, 403)


async def test_browsing_needs_a_brand_login(platform, make_merchant):
    plain = await make_merchant("browse@brands.example.com")

    assert (await platform.get(LIBRARY)).status_code in (401, 404)
    assert (await platform.get(LIBRARY, headers=plain.headers)).status_code in (401, 404)


async def test_names_are_unique_and_fields_validated(platform, platform_admin):
    model = await _create(platform, platform_admin)
    # The duplicate's rollback expires ORM objects shared with the app; read headers once.
    headers = platform_admin.headers

    duplicate = await platform.post(
        LIBRARY, json={"name": model["name"], "gender_presentation": "FEMININE"}, headers=headers
    )
    bad_gender = await platform.post(LIBRARY, json={"name": "Z1", "gender_presentation": "X"}, headers=headers)
    bad_garment = await platform.post(
        LIBRARY,
        json={"name": "Z2", "gender_presentation": "FEMININE", "supported_garments": ["hats"]},
        headers=headers,
    )
    blank = await platform.post(LIBRARY, json={"name": "  ", "gender_presentation": "FEMININE"}, headers=headers)

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "VIRTUAL_MODEL_NAME_TAKEN"
    assert bad_gender.status_code == 422
    assert bad_garment.status_code == 422
    assert blank.status_code == 422


async def test_poses_can_be_added_and_removed(platform, platform_admin):
    model = await _create(platform, platform_admin)
    await _photo(platform, platform_admin, model["id"])

    added = await _photo(platform, platform_admin, model["id"], primary=False, label="Side")
    poses = added.json()["data"]["poses"]
    removed = await platform.delete(f"{ADMIN}/{model['id']}/poses/{poses[0]['id']}", headers=platform_admin.headers)
    again = await platform.delete(f"{ADMIN}/{model['id']}/poses/{poses[0]['id']}", headers=platform_admin.headers)
    after = await platform.get(f"{ADMIN}/{model['id']}", headers=platform_admin.headers)

    assert len(poses) == 1 and poses[0]["label"] == "Side"
    assert removed.status_code == 204
    assert again.status_code == 404
    assert after.json()["data"]["poses"] == []
    assert after.json()["data"]["image_url"]


async def test_model_photos_are_validated(platform, platform_admin):
    model = await _create(platform, platform_admin)

    response = await platform.post(
        f"{ADMIN}/{model['id']}/images",
        data={"primary": "true"},
        files={"file": ("x.png", b"not an image", "image/png")},
        headers=platform_admin.headers,
    )

    assert response.status_code == 400
