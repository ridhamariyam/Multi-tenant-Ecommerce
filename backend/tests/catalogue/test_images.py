"""Product images: ordering, the primary image, and the last-image rule."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select

from app.catalogue.models import ProductImage
from app.catalogue.service import ProductImageService
from tests.catalogue.factories import IMAGE, IMAGES, PRODUCTS
from tests.helpers import run_concurrently, succeeded


def images_of(product_id) -> str:
    return f"{PRODUCTS}/{product_id}/images"


async def test_a_product_can_hold_several_images_in_sort_order(product_with_images):
    _product, images = await product_with_images(3)

    assert len(images) == 3
    assert [image["sort_order"] for image in images] == [0, 1, 2]


async def test_an_image_can_be_added(client, admin_headers, product):
    response = await client.post(
        images_of(product["id"]), json=IMAGE, headers=admin_headers
    )

    assert response.status_code == 201
    assert response.json()["data"]["url"] == IMAGE["url"]


async def test_an_invalid_url_is_rejected(client, admin_headers, product):
    response = await client.post(
        images_of(product["id"]), json={"url": "not-a-valid-url"}, headers=admin_headers
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "url"


async def test_alt_text_can_be_updated(client, admin_headers, product_with_images):
    _product, images = await product_with_images(2)

    response = await client.patch(
        f"{IMAGES}/{images[0]['id']}",
        json={"alt_text": "  Model wearing the dress  "},
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert response.json()["data"]["alt_text"] == "Model wearing the dress"


async def test_an_image_can_be_deleted(client, admin_headers, product_with_images):
    _product, images = await product_with_images(3)

    response = await client.delete(f"{IMAGES}/{images[0]['id']}", headers=admin_headers)

    assert response.status_code == 204


async def test_the_last_image_cannot_be_deleted(
    client, admin_headers, product_with_images
):
    _product, images = await product_with_images(1)

    response = await client.delete(f"{IMAGES}/{images[0]['id']}", headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["message"] == "A product must have at least one image"


async def test_deleting_the_primary_image_promotes_another(
    client, admin_headers, product_with_images
):
    product, images = await product_with_images(3)
    primary = next(image for image in images if image["is_primary"])

    await client.delete(f"{IMAGES}/{primary['id']}", headers=admin_headers)

    response = await client.get(images_of(product["id"]), headers=admin_headers)
    remaining = response.json()["data"]
    assert sum(1 for image in remaining if image["is_primary"]) == 1


async def test_setting_a_primary_demotes_the_previous_one(
    client, admin_headers, product_with_images
):
    product, images = await product_with_images(3)

    response = await client.post(
        f"{IMAGES}/{images[2]['id']}/primary", headers=admin_headers
    )

    assert response.status_code == 200
    listed = (await client.get(images_of(product["id"]), headers=admin_headers)).json()
    primaries = [image["id"] for image in listed["data"] if image["is_primary"]]
    assert primaries == [images[2]["id"]]


async def test_images_can_be_reordered(client, admin_headers, product_with_images):
    product, images = await product_with_images(3)
    reversed_order = list(reversed(images))

    response = await client.put(
        f"{images_of(product['id'])}/order",
        json={
            "images": [
                {"id": image["id"], "sort_order": position}
                for position, image in enumerate(reversed_order)
            ]
        },
        headers=admin_headers,
    )

    assert response.status_code == 200
    assert [image["id"] for image in response.json()["data"]] == [
        image["id"] for image in reversed_order
    ]


async def test_reordering_rejects_an_image_from_another_product(
    client, admin_headers, product_with_images
):
    product_a, _images_a = await product_with_images(2)
    _product_b, images_b = await product_with_images(2)

    response = await client.put(
        f"{images_of(product_a['id'])}/order",
        json={"images": [{"id": images_b[0]["id"], "sort_order": 0}]},
        headers=admin_headers,
    )

    assert response.status_code == 404


async def test_an_image_cannot_be_added_to_an_archived_product(
    client, admin_headers, product_with_images
):
    product, _images = await product_with_images(2)
    await client.delete(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    response = await client.post(
        images_of(product["id"]), json=IMAGE, headers=admin_headers
    )

    assert response.status_code == 409


async def test_another_tenants_image_cannot_be_updated(
    other_client, other_admin_headers, product_with_images
):
    _product, images = await product_with_images(2)

    response = await other_client.patch(
        f"{IMAGES}/{images[0]['id']}",
        json={"alt_text": "stolen"},
        headers=other_admin_headers,
    )

    assert response.status_code == 404


async def test_another_tenants_image_cannot_be_deleted(
    other_client, other_admin_headers, product_with_images
):
    _product, images = await product_with_images(2)

    response = await other_client.delete(
        f"{IMAGES}/{images[0]['id']}", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_concurrent_primary_updates_leave_exactly_one_primary(
    engine, session, tenant, product_with_images
):
    """The partial unique index is what makes this safe, not the Python."""
    product, images = await product_with_images(4)

    async def claim(db, index):
        return await ProductImageService(db, tenant.id).set_primary(
            UUID(images[index]["id"])
        )

    await run_concurrently(engine, len(images), claim)

    primaries = await session.scalar(
        select(func.count())
        .select_from(ProductImage)
        .where(
            ProductImage.tenant_id == tenant.id,
            ProductImage.product_id == UUID(product["id"]),
            ProductImage.is_primary.is_(True),
        )
    )
    assert primaries == 1


async def test_concurrent_deletes_cannot_empty_a_product(
    engine, session, tenant, product_with_images
):
    """Two deletes racing on a two-image product must leave one behind."""
    product, images = await product_with_images(2)

    async def remove(db, index):
        return await ProductImageService(db, tenant.id).delete(UUID(images[index]["id"]))

    results = await run_concurrently(engine, len(images), remove)

    assert len(succeeded(results)) == 1
    remaining = await session.scalar(
        select(func.count())
        .select_from(ProductImage)
        .where(
            ProductImage.tenant_id == tenant.id,
            ProductImage.product_id == UUID(product["id"]),
        )
    )
    assert remaining == 1
