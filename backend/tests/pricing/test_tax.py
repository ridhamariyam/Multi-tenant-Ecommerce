"""One percentage, charged on the goods and the delivery together."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete

from app.pricing.models import GstSettings
from tests.pricing.conftest import CHECKOUT, TAX, tax_payload


async def test_tax_settings_can_be_read(client, staff_headers):
    response = await client.get(TAX, headers=staff_headers)

    assert response.status_code == 200, response.text
    body = response.json()["data"]
    assert Decimal(body["tax_percentage"]) == Decimal("0.00")
    assert body["is_active"] is False


async def test_an_admin_updates_tax(client, admin_headers, set_tax):
    await set_tax()

    response = await client.get(TAX, headers=admin_headers)

    body = response.json()["data"]
    assert Decimal(body["tax_percentage"]) == Decimal("18.00")
    assert body["is_active"] is True


async def test_updating_twice_keeps_one_configuration(client, admin_headers, set_tax):
    await set_tax()
    await set_tax(tax_percentage="5.00")

    response = await client.get(TAX, headers=admin_headers)

    assert Decimal(response.json()["data"]["tax_percentage"]) == Decimal("5.00")


async def test_staff_may_not_update_tax(client, staff_headers):
    response = await client.put(TAX, json=tax_payload(), headers=staff_headers)

    assert response.status_code == 403


async def test_a_customer_may_not_read_or_update_tax(client, customer_auth):
    read = await client.get(TAX, headers=customer_auth)
    write = await client.put(TAX, json=tax_payload(), headers=customer_auth)

    assert read.status_code == 403
    assert write.status_code == 403


async def test_an_anonymous_caller_is_refused(client, tenant):
    assert (await client.get(TAX)).status_code == 401
    assert (await client.put(TAX, json=tax_payload())).status_code == 401


async def test_a_negative_tax_percentage_is_rejected(client, admin_headers):
    response = await client.put(
        TAX, json=tax_payload(tax_percentage="-1.00"), headers=admin_headers
    )

    assert response.status_code == 422


async def test_a_tax_percentage_over_one_hundred_is_rejected(client, admin_headers):
    response = await client.put(
        TAX, json=tax_payload(tax_percentage="101.00"), headers=admin_headers
    )

    assert response.status_code == 422


async def test_tax_settings_are_per_tenant(other_client, other_admin_headers, set_tax):
    await set_tax()

    response = await other_client.get(TAX, headers=other_admin_headers)

    assert response.status_code == 200, response.text
    assert response.json()["data"]["is_active"] is False


async def test_one_tenants_update_does_not_touch_another(
    client, other_client, admin_headers, other_admin_headers, set_tax
):
    await set_tax()
    await other_client.put(
        TAX, json=tax_payload(tax_percentage="5.00"), headers=other_admin_headers
    )

    zeen = await client.get(TAX, headers=admin_headers)
    acme = await other_client.get(TAX, headers=other_admin_headers)

    assert Decimal(zeen.json()["data"]["tax_percentage"]) == Decimal("18.00")
    assert Decimal(acme.json()["data"]["tax_percentage"]) == Decimal("5.00")


async def test_tax_is_charged_on_the_goods(set_shipping, set_tax, fill_cart, preview):
    await set_shipping(is_active=False)
    await set_tax()
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["tax_amount"]) == Decimal("180.00")
    assert Decimal(body["total_amount"]) == Decimal("1180.00")


async def test_tax_includes_the_delivery_charge(
    set_shipping, set_tax, fill_cart, preview
):
    """The worked example: 2000 goods + 100 delivery at 18% is 2478.00."""
    await set_shipping(free_shipping_minimum=None)
    await set_tax()
    await fill_cart(2)

    body = await preview()

    assert Decimal(body["subtotal"]) == Decimal("2000.00")
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert Decimal(body["tax_amount"]) == Decimal("378.00")
    assert Decimal(body["total_amount"]) == Decimal("2478.00")


async def test_zero_tax_works(set_shipping, set_tax, fill_cart, preview):
    await set_shipping(is_active=False)
    await set_tax(tax_percentage="0.00")
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["tax_amount"]) == Decimal("0.00")
    assert Decimal(body["total_amount"]) == Decimal("1000.00")


async def test_switching_tax_off_charges_none(set_shipping, set_tax, fill_cart, preview):
    await set_shipping(is_active=False)
    await set_tax(is_active=False)
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["tax_amount"]) == Decimal("0.00")


async def test_an_unconfigured_tenant_still_prices_a_basket(
    client, session, tenant, customer_auth, set_shipping, fill_cart
):
    """Without GST settings checkout no longer stops: it prices on the defaults
    (here the signed-off 0% mappings still win) and flags nothing as verified."""
    await set_shipping(is_active=False)
    await fill_cart(1)
    await session.execute(delete(GstSettings).where(GstSettings.tenant_id == tenant.id))
    await session.commit()

    response = await client.post(f"{CHECKOUT}/preview", headers=customer_auth)

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["data"]["tax_amount"]) == Decimal("0.00")


async def test_tax_is_rounded_to_two_places(set_shipping, set_tax, fill_cart, preview):
    """1000.00 at 7.55% is 75.50 exactly; 3 x 1000 at 7.55% is 226.50."""
    await set_shipping(is_active=False)
    await set_tax(tax_percentage="7.55")
    await fill_cart(3)

    body = await preview()

    assert Decimal(body["tax_amount"]) == Decimal("226.50")
    assert Decimal(body["total_amount"]) == Decimal("3226.50")


async def test_a_fractional_tax_rounds_half_up(set_shipping, set_tax, fill_cart, preview):
    """1000.00 at 0.125% is 1.25 exactly; at 0.13% it is 1.30."""
    await set_shipping(is_active=False)
    await set_tax(tax_percentage="0.13")
    await fill_cart(1)

    body = await preview()

    assert Decimal(body["tax_amount"]) == Decimal("1.30")
