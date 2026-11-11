"""Free shipping, BOGO, first-order, category, automatic and volume discounts."""

from __future__ import annotations

from decimal import Decimal

from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.orders.conftest import CHECKOUT

COUPONS = "/api/v1/admin/coupons"
APPLY = "/api/v1/coupons/apply"
OFFERS = "/api/v1/coupons/offers"
SHIPPING = "/api/v1/admin/shipping"


async def _coupon(client, headers, expect=200, **fields):
    response = await client.post(COUPONS, json=fields, headers=headers)
    assert response.status_code == expect, response.text
    return response.json()


async def _preview(client, headers, code=None):
    params = {"coupon_code": code} if code else {}
    response = await client.post(f"{CHECKOUT}/preview", params=params, headers=headers)
    return response


async def _variant_in(client, admin_headers, category, price, sku):
    product = await make_product(client, admin_headers, category["id"], status="ACTIVE")
    response = await client.post(
        f"{PRODUCTS}/{product['id']}/variants",
        json={"sku": sku, "name": "Std", "price": price, "status": "ACTIVE", "initial_quantity": 20},
        headers=admin_headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


# ------------------------------------------------------------------ creation


async def test_free_shipping_needs_no_value(client, admin_headers):
    body = await _coupon(client, admin_headers, code="SHIPFREE", discount_type="FREE_SHIPPING")

    assert body["data"]["discount_type"] == "FREE_SHIPPING"
    assert Decimal(body["data"]["discount_value"]) == Decimal("0.00")


async def test_a_percentage_coupon_still_needs_a_value(client, admin_headers):
    body = await _coupon(client, admin_headers, expect=400, code="NOVALUE", discount_type="PERCENTAGE")

    assert "discount_value" in body["message"]


async def test_bogo_needs_both_quantities(client, admin_headers):
    await _coupon(
        client, admin_headers, expect=400, code="BOGOBAD", discount_type="BOGO",
        discount_value="100", buy_quantity=1,
    )


async def test_an_unknown_category_is_rejected(client, admin_headers):
    await _coupon(
        client, admin_headers, expect=404, code="NOCAT", discount_type="PERCENTAGE",
        discount_value="10", category_ids=["00000000-0000-0000-0000-000000000000"],
    )


# ------------------------------------------------------------------ checkout


async def test_free_shipping_removes_the_delivery_charge(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await client.put(
        SHIPPING, json={"shipping_amount": "100.00", "free_shipping_minimum": None},
        headers=admin_headers,
    )
    await _coupon(client, admin_headers, code="SHIPFREE", discount_type="FREE_SHIPPING")
    await add_to_cart(customer_auth, variant["id"], 1)

    body = (await _preview(client, customer_auth, "SHIPFREE")).json()["data"]

    assert Decimal(body["shipping_amount"]) == Decimal("0.00")
    assert Decimal(body["shipping_discount"]) == Decimal("100.00")
    assert Decimal(body["discount_amount"]) == Decimal("0.00")


async def test_bogo_makes_the_cheaper_item_free(
    client, admin_headers, customer_auth, add_to_cart, tax_ready
):
    category = await make_category(client, admin_headers, name="BOGO Cat")
    dear = await _variant_in(client, admin_headers, category, "1000.00", "BOGO-DEAR")
    cheap = await _variant_in(client, admin_headers, category, "600.00", "BOGO-CHEAP")
    await _coupon(
        client, admin_headers, code="B1G1", discount_type="BOGO", discount_value="100",
        buy_quantity=1, get_quantity=1,
    )
    await add_to_cart(customer_auth, dear["id"], 1)
    await add_to_cart(customer_auth, cheap["id"], 1)

    body = (await _preview(client, customer_auth, "B1G1")).json()["data"]

    assert Decimal(body["discount_amount"]) == Decimal("600.00")


async def test_bogo_needs_enough_items(client, admin_headers, customer_auth, variant, add_to_cart):
    await _coupon(
        client, admin_headers, code="B2G1", discount_type="BOGO", discount_value="100",
        buy_quantity=2, get_quantity=1,
    )
    await add_to_cart(customer_auth, variant["id"], 2)

    response = await _preview(client, customer_auth, "B2G1")

    assert response.status_code == 400


async def test_a_half_price_bogo(client, admin_headers, customer_auth, variant, add_to_cart):
    await _coupon(
        client, admin_headers, code="B1G1HALF", discount_type="BOGO", discount_value="50",
        buy_quantity=1, get_quantity=1,
    )
    await add_to_cart(customer_auth, variant["id"], 2)

    body = (await _preview(client, customer_auth, "B1G1HALF")).json()["data"]

    assert Decimal(body["discount_amount"]) == Decimal("499.50")


async def test_a_first_order_coupon_works_only_once(
    client, admin_headers, customer_auth, variant, add_to_cart, address, place_order
):
    await _coupon(
        client, admin_headers, code="WELCOME10", discount_type="PERCENTAGE",
        discount_value="10", first_order_only=True,
    )
    await add_to_cart(customer_auth, variant["id"], 1)
    first = await place_order(customer_auth, address["id"], coupon_code="WELCOME10")
    await add_to_cart(customer_auth, variant["id"], 1)

    second = await _preview(client, customer_auth, "WELCOME10")

    assert first.status_code == 201
    assert Decimal(first.json()["data"]["discount_amount"]) == Decimal("99.90")
    assert second.status_code == 400
    assert "first order" in second.json()["message"]


async def test_a_category_coupon_discounts_only_that_category(
    client, admin_headers, customer_auth, add_to_cart, tax_ready
):
    ethnic = await make_category(client, admin_headers, name="Ethnic")
    kurtas = await make_category(client, admin_headers, name="Kurtas", parent_id=ethnic["id"])
    casual = await make_category(client, admin_headers, name="Casual")
    kurta = await _variant_in(client, admin_headers, kurtas, "1000.00", "CAT-KURTA")
    tee = await _variant_in(client, admin_headers, casual, "500.00", "CAT-TEE")
    await _coupon(
        client, admin_headers, code="ETHNIC20", discount_type="PERCENTAGE",
        discount_value="20", category_ids=[ethnic["id"]],
    )
    await add_to_cart(customer_auth, kurta["id"], 1)
    await add_to_cart(customer_auth, tee["id"], 1)

    body = (await _preview(client, customer_auth, "ETHNIC20")).json()["data"]

    assert Decimal(body["discount_amount"]) == Decimal("200.00")


async def test_a_category_coupon_with_nothing_eligible_fails(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    other = await make_category(client, admin_headers, name="Elsewhere")
    await _coupon(
        client, admin_headers, code="ONLYTHERE", discount_type="FIXED_AMOUNT",
        discount_value="50", category_ids=[other["id"]],
    )
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await _preview(client, customer_auth, "ONLYTHERE")

    assert response.status_code == 400


async def test_a_volume_discount_needs_the_quantity(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(
        client, admin_headers, code="BUY2", discount_type="PERCENTAGE",
        discount_value="15", min_quantity=2,
    )
    await add_to_cart(customer_auth, variant["id"], 1)
    too_few = await _preview(client, customer_auth, "BUY2")
    await add_to_cart(customer_auth, variant["id"], 1)
    enough = await _preview(client, customer_auth, "BUY2")

    assert too_few.status_code == 400
    assert Decimal(enough.json()["data"]["discount_amount"]) == Decimal("299.70")


async def test_an_automatic_discount_applies_without_a_code(
    client, admin_headers, customer_auth, variant, add_to_cart, address, place_order
):
    await _coupon(
        client, admin_headers, code="FESTIVE30", discount_type="PERCENTAGE",
        discount_value="30", is_automatic=True,
    )
    await add_to_cart(customer_auth, variant["id"], 1)

    preview = (await _preview(client, customer_auth)).json()["data"]
    order = (await place_order(customer_auth, address["id"])).json()["data"]

    assert preview["coupon_code"] == "FESTIVE30"
    assert preview["is_automatic_discount"] is True
    assert Decimal(preview["discount_amount"]) == Decimal("299.70")
    assert order["coupon_code"] == "FESTIVE30"


async def test_the_best_automatic_discount_wins(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(client, admin_headers, code="AUTO10", discount_type="PERCENTAGE",
                  discount_value="10", is_automatic=True)
    await _coupon(client, admin_headers, code="AUTO200", discount_type="FIXED_AMOUNT",
                  discount_value="200", is_automatic=True)
    await add_to_cart(customer_auth, variant["id"], 1)

    body = (await _preview(client, customer_auth)).json()["data"]

    assert body["coupon_code"] == "AUTO200"


async def test_an_automatic_volume_offer_kicks_in_at_the_quantity(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(client, admin_headers, code="BUY2AUTO", discount_type="PERCENTAGE",
                  discount_value="15", min_quantity=2, is_automatic=True)
    await add_to_cart(customer_auth, variant["id"], 1)
    one = (await _preview(client, customer_auth)).json()["data"]
    await add_to_cart(customer_auth, variant["id"], 1)
    two = (await _preview(client, customer_auth)).json()["data"]

    assert one["coupon_code"] is None
    assert two["coupon_code"] == "BUY2AUTO"


async def test_a_typed_code_replaces_the_automatic_discount(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(client, admin_headers, code="AUTO30", discount_type="PERCENTAGE",
                  discount_value="30", is_automatic=True)
    await _coupon(client, admin_headers, code="FLAT50", discount_type="FIXED_AMOUNT",
                  discount_value="50")
    await add_to_cart(customer_auth, variant["id"], 1)

    body = (await _preview(client, customer_auth, "FLAT50")).json()["data"]

    assert body["coupon_code"] == "FLAT50"
    assert body["is_automatic_discount"] is False
    assert Decimal(body["discount_amount"]) == Decimal("50.00")


async def test_apply_checks_basket_rules_against_the_cart(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(client, admin_headers, code="BUY3", discount_type="PERCENTAGE",
                  discount_value="10", min_quantity=3)
    empty = await client.post(APPLY, json={"code": "BUY3"}, headers=customer_auth)
    await add_to_cart(customer_auth, variant["id"], 1)
    short = await client.post(APPLY, json={"code": "BUY3"}, headers=customer_auth)
    await add_to_cart(customer_auth, variant["id"], 2)
    full = await client.post(APPLY, json={"code": "BUY3"}, headers=customer_auth)

    assert empty.status_code == 409
    assert short.status_code == 400
    assert Decimal(full.json()["data"]["discount_amount"]) == Decimal("299.70")


async def test_apply_reports_free_shipping(
    client, admin_headers, customer_auth, variant, add_to_cart
):
    await _coupon(client, admin_headers, code="SHIPIT", discount_type="FREE_SHIPPING")
    await add_to_cart(customer_auth, variant["id"], 1)

    response = await client.post(APPLY, json={"code": "SHIPIT"}, headers=customer_auth)

    assert response.json()["data"]["free_shipping"] is True


async def test_offers_list_running_automatic_discounts(client, admin_headers, tenant):
    await _coupon(client, admin_headers, code="LIVEAUTO", discount_type="PERCENTAGE",
                  discount_value="5", is_automatic=True)
    await _coupon(client, admin_headers, code="CODEONLY", discount_type="PERCENTAGE",
                  discount_value="5")
    await _coupon(client, admin_headers, code="OFFAUTO", discount_type="PERCENTAGE",
                  discount_value="5", is_automatic=True, is_active=False)

    response = await client.get(OFFERS)

    assert [o["code"] for o in response.json()["data"]] == ["LIVEAUTO"]


async def test_category_ids_are_returned_and_replaced(client, admin_headers):
    first = await make_category(client, admin_headers, name="First Cat")
    second = await make_category(client, admin_headers, name="Second Cat")
    created = (await _coupon(client, admin_headers, code="CATS", discount_type="PERCENTAGE",
                             discount_value="5", category_ids=[first["id"]]))["data"]

    updated = await client.put(
        f"{COUPONS}/{created['id']}", json={"category_ids": [second["id"]]}, headers=admin_headers
    )

    assert created["category_ids"] == [first["id"]]
    assert updated.json()["data"]["category_ids"] == [second["id"]]
