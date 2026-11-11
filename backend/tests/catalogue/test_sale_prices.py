"""Scheduled sale prices: charged inside the window, regular price outside it."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from tests.catalogue.factories import PRODUCTS, STOREFRONT, VARIANTS


def _iso(delta: timedelta) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat()


async def test_a_running_sale_sets_the_effective_price(new_variant):
    variant = await new_variant(
        sale_price="80.00", sale_starts_at=_iso(-timedelta(hours=1)), sale_ends_at=_iso(timedelta(days=1))
    )

    assert variant["is_on_sale"] is True
    assert Decimal(variant["effective_price"]) == Decimal("80.00")
    assert Decimal(variant["price"]) == Decimal("100.00")


async def test_a_future_sale_does_not_apply_yet(new_variant):
    variant = await new_variant(sale_price="80.00", sale_starts_at=_iso(timedelta(days=1)))

    assert variant["is_on_sale"] is False
    assert Decimal(variant["effective_price"]) == Decimal("100.00")


async def test_an_ended_sale_reverts_to_the_regular_price(new_variant):
    variant = await new_variant(
        sale_price="80.00",
        sale_starts_at=_iso(-timedelta(days=3)),
        sale_ends_at=_iso(-timedelta(days=1)),
    )

    assert variant["is_on_sale"] is False
    assert Decimal(variant["effective_price"]) == Decimal("100.00")


async def test_a_sale_price_must_undercut_the_regular_price(client, admin_headers, product):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "SALE-HIGH", "name": "High", "price": "100.00", "sale_price": "120.00"},
        headers=admin_headers,
    )

    assert response.status_code == 400


async def test_a_sale_must_start_before_it_ends(client, admin_headers, product):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={
            "sku": "SALE-BACKWARDS",
            "name": "Backwards",
            "price": "100.00",
            "sale_price": "80.00",
            "sale_starts_at": _iso(timedelta(days=2)),
            "sale_ends_at": _iso(timedelta(days=1)),
        },
        headers=admin_headers,
    )

    assert response.status_code == 400


async def test_a_window_without_a_sale_price_is_rejected(client, admin_headers, product):
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": "SALE-NOPRICE", "name": "No price", "price": "100.00", "sale_ends_at": _iso(timedelta(days=1))},
        headers=admin_headers,
    )

    assert response.status_code == 400


async def test_ending_a_sale_early_clears_its_window(client, admin_headers, new_variant):
    variant = await new_variant(sale_price="80.00", sale_ends_at=_iso(timedelta(days=5)))

    response = await client.patch(
        f"{VARIANTS}/{variant['id']}", json={"sale_price": None}, headers=admin_headers
    )

    body = response.json()["data"]
    assert response.status_code == 200
    assert body["sale_price"] is None
    assert body["sale_ends_at"] is None
    assert Decimal(body["effective_price"]) == Decimal("100.00")


async def test_the_storefront_shows_the_sale_and_the_regular_price(
    client, admin_headers, publish
):
    product = await publish(name="Sale Kurta", price="1000.00")
    variants = await client.get(f"{PRODUCTS}/{product['id']}/variants", headers=admin_headers)
    variant_id = variants.json()["data"][0]["id"]
    await client.patch(
        f"{VARIANTS}/{variant_id}",
        json={"sale_price": "750.00", "sale_ends_at": _iso(timedelta(days=2))},
        headers=admin_headers,
    )

    detail = await client.get(f"{STOREFRONT}/products/{product['id']}")
    listing = await client.get(f"{STOREFRONT}/products", params={"search": "Sale Kurta"})

    shown = detail.json()["data"]["variants"][0]
    assert Decimal(shown["price"]) == Decimal("750.00")
    assert Decimal(shown["compare_at_price"]) == Decimal("1000.00")
    assert shown["sale_ends_at"] is not None
    row = listing.json()["data"][0]
    assert Decimal(row["price_from"]) == Decimal("750.00")
    assert row["on_sale"] is True


async def test_price_filters_and_sorting_use_the_sale_price(client, admin_headers, publish):
    cheap_on_sale = await publish(name="Sorted Sale", price="900.00")
    await publish(name="Sorted Regular", price="500.00")
    variants = await client.get(
        f"{PRODUCTS}/{cheap_on_sale['id']}/variants", headers=admin_headers
    )
    await client.patch(
        f"{VARIANTS}/{variants.json()['data'][0]['id']}",
        json={"sale_price": "300.00"},
        headers=admin_headers,
    )

    under_400 = await client.get(
        f"{STOREFRONT}/products", params={"search": "Sorted", "max_price": "400"}
    )
    cheapest_first = await client.get(
        f"{STOREFRONT}/products", params={"search": "Sorted", "sort": "price_low"}
    )

    assert [p["id"] for p in under_400.json()["data"]] == [cheap_on_sale["id"]]
    assert cheapest_first.json()["data"][0]["id"] == cheap_on_sale["id"]
