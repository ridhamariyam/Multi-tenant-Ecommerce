"""Builders for catalogue fixtures."""

from __future__ import annotations

import copy

from tests.helpers import load_data, sample

DATA = load_data(__file__)

CATEGORIES = DATA["routes"]["categories"]
PRODUCTS = DATA["routes"]["products"]
VARIANTS = DATA["routes"]["variants"]
IMAGES = DATA["routes"]["images"]
INVENTORY = DATA["routes"]["inventory"]
STOREFRONT = DATA["routes"]["storefront"]

IMAGE = DATA["image"]


def inventory_url(variant_id, action: str = "") -> str:
    """/catalogue/variants/{id}/inventory, optionally with /adjust etc."""
    url = INVENTORY.format(variant_id=variant_id)
    return f"{url}/{action}" if action else url


def image(**overrides) -> dict:
    return sample(DATA, "image", **overrides)


async def make_category(client, headers, **overrides) -> dict:
    payload = sample(DATA, "category", **overrides)
    response = await client.post(CATEGORIES, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def make_product(client, headers, category_id, **overrides) -> dict:
    payload = sample(DATA, "product", category_id=category_id, **overrides)
    payload.setdefault("images", [copy.deepcopy(IMAGE)])
    response = await client.post(PRODUCTS, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def make_variant(client, headers, product_id, **overrides) -> dict:
    payload = sample(DATA, "variant", **overrides)
    response = await client.post(
        f"{PRODUCTS}/{product_id}/variants", json=payload, headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]
