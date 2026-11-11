"""Product-page information: size chart, fabric/care/origin, HSN and GST rate."""

from __future__ import annotations

from decimal import Decimal

from tests.catalogue.factories import CATEGORIES, PRODUCTS, STOREFRONT, make_category, make_product

SIZE_CHART = {
    "unit": "in",
    "measurements": ["Bust", "Waist"],
    "rows": [
        {"size": "S", "values": {"Bust": "34", "Waist": "28"}},
        {"size": "M", "values": {"Bust": "36", "Waist": "30"}},
    ],
    "note": "Garment measurements",
}

INFO = {
    "fabric_details": "100% cotton, 60s count, soft hand-feel",
    "washing_instructions": "Hand wash cold. Dry in shade.",
    "country_of_origin": "India",
}


async def test_a_product_stores_its_information_blocks(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], **INFO)

    response = await client.get(f"{PRODUCTS}/{product['id']}", headers=admin_headers)

    body = response.json()["data"]
    for field, value in INFO.items():
        assert body[field] == value


async def test_the_size_chart_reads_back_in_inches_and_centimetres(
    client, admin_headers, category
):
    product = await make_product(client, admin_headers, category["id"], size_chart=SIZE_CHART)

    chart = product["size_chart"]
    assert chart["unit"] == "in"
    assert chart["measurements"] == ["Bust", "Waist"]
    small = chart["rows"][0]
    assert small["size"] == "S"
    assert Decimal(small["values_in"]["Bust"]) == Decimal("34.0")
    assert Decimal(small["values_cm"]["Bust"]) == Decimal("86.4")


async def test_a_centimetre_chart_converts_to_inches(client, admin_headers, category):
    chart = {**SIZE_CHART, "unit": "cm", "rows": [{"size": "S", "values": {"Bust": "86.4"}}]}
    product = await make_product(client, admin_headers, category["id"], size_chart=chart)

    row = product["size_chart"]["rows"][0]
    assert Decimal(row["values_cm"]["Bust"]) == Decimal("86.4")
    assert Decimal(row["values_in"]["Bust"]) == Decimal("34.0")


async def test_a_size_chart_row_cannot_use_an_unknown_measurement(
    client, admin_headers, category
):
    chart = {**SIZE_CHART, "rows": [{"size": "S", "values": {"Hip": "38"}}]}

    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Bad Chart",
            "size_chart": chart,
            "images": [{"url": "https://cdn.example.com/a.jpg"}],
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_size_chart_rejects_duplicate_sizes(client, admin_headers, category):
    rows = [{"size": "S", "values": {"Bust": "34"}}, {"size": "s", "values": {"Bust": "35"}}]

    response = await client.post(
        PRODUCTS,
        json={
            "category_id": category["id"],
            "name": "Twice Small",
            "size_chart": {**SIZE_CHART, "rows": rows},
            "images": [{"url": "https://cdn.example.com/a.jpg"}],
        },
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_the_size_chart_can_be_removed(client, admin_headers, category):
    product = await make_product(client, admin_headers, category["id"], size_chart=SIZE_CHART)

    response = await client.patch(
        f"{PRODUCTS}/{product['id']}", json={"size_chart": None}, headers=admin_headers
    )

    assert response.json()["data"]["size_chart"] is None


async def test_the_storefront_shows_the_information_and_chart(client, publish):
    product = await publish(name="Info Kurta", size_chart=SIZE_CHART, **INFO)

    response = await client.get(f"{STOREFRONT}/products/{product['id']}")

    body = response.json()["data"]
    assert body["washing_instructions"] == INFO["washing_instructions"]
    assert body["country_of_origin"] == "India"
    assert body["size_chart"]["rows"][1]["size"] == "M"
    assert "hsn_code" not in body


async def test_hsn_and_gst_rate_on_a_category_and_product(client, admin_headers):
    category = await make_category(
        client, admin_headers, name="Taxed", hsn_code="6204", gst_rate="5.00"
    )
    product = await make_product(
        client, admin_headers, category["id"], hsn_code="62044290", gst_rate="12.00"
    )

    fetched = await client.get(f"{CATEGORIES}/{category['id']}", headers=admin_headers)

    assert fetched.json()["data"]["hsn_code"] == "6204"
    assert Decimal(fetched.json()["data"]["gst_rate"]) == Decimal("5.00")
    assert product["hsn_code"] == "62044290"
    assert Decimal(product["gst_rate"]) == Decimal("12.00")


async def test_an_hsn_code_must_be_4_6_or_8_digits(client, admin_headers, category):
    response = await client.patch(
        f"{PRODUCTS}/{(await make_product(client, admin_headers, category['id']))['id']}",
        json={"hsn_code": "62A4"},
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_gst_rate_above_100_is_rejected(client, admin_headers):
    response = await client.post(
        CATEGORIES, json={"name": "Over Taxed", "gst_rate": "120"}, headers=admin_headers
    )

    assert response.status_code == 422
