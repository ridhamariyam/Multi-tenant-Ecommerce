"""The delivery charge, and the threshold that makes it free."""

from __future__ import annotations

from decimal import Decimal

from tests.pricing.conftest import SHIPPING, shipping_payload


async def test_shipping_settings_can_be_read(client, staff_headers):
    response = await client.get(SHIPPING, headers=staff_headers)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert Decimal(body["shipping_amount"]) == Decimal("0.00")
    assert body["free_shipping_minimum"] is None
    assert body["is_active"] is False


async def test_an_admin_updates_shipping(client, admin_headers, set_shipping):
    await set_shipping()

    response = await client.get(SHIPPING, headers=admin_headers)

    body = response.json()["data"]
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["free_shipping_minimum"]) == Decimal("2000.00")
    assert body["is_active"] is True


async def test_updating_twice_keeps_one_configuration(client, admin_headers, set_shipping):
    await set_shipping()
    await set_shipping(shipping_amount="75.00", free_shipping_minimum=None)

    response = await client.get(SHIPPING, headers=admin_headers)

    body = response.json()["data"]
    assert Decimal(body["shipping_amount"]) == Decimal("75.00")
    assert body["free_shipping_minimum"] is None


async def test_staff_may_not_update_shipping(client, staff_headers):
    response = await client.put(SHIPPING, json=shipping_payload(), headers=staff_headers)

    assert response.status_code == 403


async def test_a_customer_may_not_read_or_update_shipping(client, customer_auth):
    read = await client.get(SHIPPING, headers=customer_auth)
    write = await client.put(SHIPPING, json=shipping_payload(), headers=customer_auth)

    assert read.status_code == 403
    assert write.status_code == 403


async def test_an_anonymous_caller_is_refused(client, tenant):
    assert (await client.get(SHIPPING)).status_code == 401
    assert (await client.put(SHIPPING, json=shipping_payload())).status_code == 401


async def test_a_negative_shipping_amount_is_rejected(client, admin_headers):
    response = await client.put(
        SHIPPING, json=shipping_payload(shipping_amount="-1.00"), headers=admin_headers
    )

    assert response.status_code == 422


async def test_a_negative_free_shipping_minimum_is_rejected(client, admin_headers):
    response = await client.put(
        SHIPPING,
        json=shipping_payload(free_shipping_minimum="-1.00"),
        headers=admin_headers,
    )

    assert response.status_code == 422


async def test_a_tenant_id_in_the_body_is_rejected(client, admin_headers, other_tenant):
    response = await client.put(
        SHIPPING,
        json=shipping_payload(tenant_id=str(other_tenant.id)),
        headers=admin_headers,
    )

    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == "tenant_id"


async def test_shipping_settings_are_per_tenant(
    other_client, other_admin_headers, set_shipping
):
    await set_shipping()

    response = await other_client.get(SHIPPING, headers=other_admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_active"] is False


async def test_one_tenants_update_does_not_touch_another(
    client, other_client, admin_headers, other_admin_headers, set_shipping
):
    await set_shipping()
    await other_client.put(
        SHIPPING,
        json=shipping_payload(shipping_amount="250.00", free_shipping_minimum=None),
        headers=other_admin_headers,
    )

    zeen = await client.get(SHIPPING, headers=admin_headers)
    acme = await other_client.get(SHIPPING, headers=other_admin_headers)

    assert Decimal(zeen.json()["data"]["shipping_amount"]) == Decimal("100.00")
    assert Decimal(acme.json()["data"]["shipping_amount"]) == Decimal("250.00")


async def test_shipping_applies_below_the_free_threshold(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping()
    await set_tax(tax_percentage="0.00")
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["subtotal"]) == Decimal("1000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")


async def test_shipping_becomes_free_at_the_threshold(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping()
    await set_tax(tax_percentage="0.00")
    await fill_cart(2)

    body = await preview()

    assert Decimal(body["subtotal"]) == Decimal("2000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("0.00")


async def test_shipping_stays_free_above_the_threshold(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping()
    await set_tax(tax_percentage="0.00")
    await fill_cart(3)

    body = await preview()

    assert Decimal(body["shipping_amount"]) == Decimal("0.00")


async def test_no_threshold_means_shipping_always_applies(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(free_shipping_minimum=None)
    await set_tax(tax_percentage="0.00")
    await fill_cart(5)

    body = await preview()

    assert Decimal(body["subtotal"]) == Decimal("5000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")


async def test_switching_shipping_off_makes_it_free(
    set_shipping, set_tax, fill_cart, preview
):
    await set_shipping(is_active=False)
    await set_tax(tax_percentage="0.00")
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["shipping_amount"]) == Decimal("0.00")


async def test_an_unconfigured_tenant_ships_free(set_tax, fill_cart, preview):
    await set_tax(tax_percentage="0.00")
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["shipping_amount"]) == Decimal("0.00")
    assert Decimal(body["total_amount"]) == Decimal("1000.00")
