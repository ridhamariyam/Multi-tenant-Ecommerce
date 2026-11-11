"""Checkout priced by the system GST defaults, before the store has configured tax."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select, update

from app.catalogue.models import Product
from app.orders.models import OrderItem
from app.pricing.defaults import ensure_default_rules
from app.pricing.models import GstDefaultRule
from app.pricing.tax_engine import TaxEngine, TaxLineInput
from tests.catalogue.factories import PRODUCTS
from tests.gst_defaults.conftest import GST, STOREFRONT_TAX


def dec(value) -> Decimal:
    return Decimal(str(value))


async def test_an_unconfigured_store_checks_out_on_the_defaults(new_variant, add_to_cart, preview):
    """Rs 2,000 before GST at the default 5%: Rs 100 tax, Rs 2,100 total."""
    await add_to_cart(await new_variant("2000.00"))

    body = await preview()

    assert dec(body["subtotal"]) == dec("2000.00")
    assert dec(body["tax_amount"]) == dec("100.00")
    assert dec(body["total_amount"]) == dec("2100.00")
    assert dec(body["items"][0]["gst_rate"]) == dec("5.00")
    # Internal review flags stay off the shopper-facing preview.
    assert "tax_verification" not in body["items"][0]


async def test_above_the_threshold_is_taxed_at_18(new_variant, add_to_cart, preview):
    await add_to_cart(await new_variant("3000.00"))

    body = await preview()

    assert dec(body["tax_amount"]) == dec("540.00")


async def test_exactly_at_the_threshold_is_taxed_at_5(new_variant, add_to_cart, preview):
    await add_to_cart(await new_variant("2500.00"))

    body = await preview()

    assert dec(body["tax_amount"]) == dec("125.00")


async def test_the_threshold_is_per_piece_not_per_line(new_variant, add_to_cart, preview):
    """Two pieces at 2,000 are 4,000 on the line, but each piece is under 2,500."""
    await add_to_cart(await new_variant("2000.00"), quantity=2)

    body = await preview()

    assert dec(body["tax_amount"]) == dec("200.00")


async def test_lines_at_different_rates_add_up(new_variant, add_to_cart, preview):
    await add_to_cart(await new_variant("2000.00"))
    await add_to_cart(await new_variant("3000.00"))

    body = await preview()

    rates = sorted(dec(item["gst_rate"]) for item in body["items"])
    assert rates == [dec("5.00"), dec("18.00")]
    assert dec(body["tax_amount"]) == dec("640.00")
    assert dec(body["total_amount"]) == dec("5640.00")


async def test_rounding_is_half_up_to_paise(new_variant, add_to_cart, preview):
    """999.99 at 5% is 49.9995, which rounds to 50.00."""
    await add_to_cart(await new_variant("999.99"))

    body = await preview()

    assert dec(body["tax_amount"]) == dec("50.00")
    assert dec(body["total_amount"]) == dec("1049.99")


async def test_inclusive_prices_extract_gst(set_gst, new_variant, add_to_cart, preview):
    """Rs 2,000 including 5%: Rs 95.24 GST inside, total stays Rs 2,000."""
    await set_gst(prices_include_gst=True)
    await add_to_cart(await new_variant("2000.00"))

    body = await preview()

    assert dec(body["tax_amount"]) == dec("95.24")
    assert dec(body["items"][0]["taxable_amount"]) == dec("1904.76")
    assert dec(body["total_amount"]) == dec("2000.00")


async def test_a_switched_off_store_charges_no_gst(set_gst, new_variant, add_to_cart, preview):
    await set_gst(gst_enabled=False)
    await add_to_cart(await new_variant("3000.00"))

    body = await preview()

    assert dec(body["tax_amount"]) == dec("0.00")


async def test_an_unregistered_store_charges_no_gst(set_gst, new_variant, add_to_cart, preview):
    await set_gst(registration_status="NOT_REGISTERED")
    await add_to_cart(await new_variant("3000.00"))

    assert dec((await preview())["tax_amount"]) == dec("0.00")


async def test_same_state_splits_cgst_and_sgst(
    set_gst, new_variant, add_to_cart, make_address, preview
):
    await set_gst(state="Kerala")
    await add_to_cart(await new_variant("2000.00"))
    address = await make_address(state="Kerala")

    gst = (await preview(address["id"]))["gst"]

    assert gst["gst_type"] == "INTRA_STATE"
    assert (dec(gst["cgst_amount"]), dec(gst["sgst_amount"]), dec(gst["igst_amount"])) == (
        dec("50.00"), dec("50.00"), dec("0.00")
    )


async def test_another_state_charges_igst(
    set_gst, new_variant, add_to_cart, make_address, preview
):
    await set_gst(state="Kerala")
    await add_to_cart(await new_variant("2000.00"))
    address = await make_address(state="Karnataka", city="Bengaluru", postal_code="560001")

    gst = (await preview(address["id"]))["gst"]

    assert gst["gst_type"] == "INTER_STATE"
    assert dec(gst["igst_amount"]) == dec("100.00")
    assert dec(gst["cgst_amount"]) == dec("0.00")


async def test_an_unclassified_hsn_falls_back_and_is_flagged(
    client, admin_headers, new_variant, add_to_cart, preview
):
    await add_to_cart(await new_variant("500.00", hsn_code="7117"))

    body = await preview()
    review = await client.get(f"{GST}/product-review?flagged=true", headers=admin_headers)

    assert dec(body["tax_amount"]) == dec("90.00")
    rows = review.json()["data"]
    assert [row["source"] for row in rows] == ["FALLBACK"]
    assert rows[0]["verification"] == "NEEDS_REVIEW"


async def test_the_order_freezes_a_full_tax_snapshot(
    set_gst, new_variant, add_to_cart, make_address, preview, place_order
):
    await set_gst(state="Kerala")
    await add_to_cart(await new_variant("3000.00", hsn_code="6204"))
    address = await make_address(state="Kerala")

    quoted = await preview(address["id"])
    order = await place_order(address["id"])

    item = order["items"][0]
    assert dec(order["total_amount"]) == dec(quoted["total_amount"]) == dec("3540.00")
    assert sum(dec(payment["amount"]) for payment in order["payments"]) == dec("3540.00")
    assert dec(item["gst_rate"]) == dec("18.00")
    assert dec(item["taxable_amount"]) == dec("3000.00")
    assert (dec(item["cgst_amount"]), dec(item["sgst_amount"])) == (dec("270.00"), dec("270.00"))
    assert item["hsn_code"] == "6204"
    assert item["tax_rule_code"] == "APPAREL_ABOVE_2500"
    assert item["tax_source"] == "SYSTEM_DEFAULT"
    assert item["tax_verification"] == "AWAITING_VERIFICATION"
    assert order["tax_review_required"] is True


async def test_a_placed_order_keeps_its_tax_when_rules_change(
    session, client, admin_headers, set_gst, new_variant, add_to_cart, make_address,
    preview, place_order,
):
    await set_gst(state="Kerala")
    variant = await new_variant("2000.00")
    await add_to_cart(variant)
    address = await make_address(state="Kerala")
    order = await place_order(address["id"])

    # The store sets its own rate, and the system rule itself is changed.
    response = await client.patch(
        f"{PRODUCTS}/{variant['product_id']}", json={"gst_rate": "12.00"}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    await session.execute(
        update(GstDefaultRule)
        .where(GstDefaultRule.code == "APPAREL_UPTO_2500")
        .values(gst_rate=Decimal("7.00"))
    )
    await session.commit()

    await add_to_cart(variant)
    assert dec((await preview())["tax_amount"]) == dec("240.00")

    saved = (
        await session.scalars(select(OrderItem).where(OrderItem.order_id == UUID(order["id"])))
    ).one()
    await session.refresh(saved)
    assert (saved.gst_rate, saved.tax_amount) == (dec("5.00"), dec("100.00"))
    assert saved.tax_rule_code == "APPAREL_UPTO_2500"


async def test_a_discount_can_bring_a_piece_under_the_threshold(session, tenant, category):
    """2,600 less a 200 discount is 2,400 per piece: taxed at 5%, not 18%."""
    product = Product(
        tenant_id=tenant.id, category_id=UUID(category["id"]), name="Anarkali", slug="anarkali",
        status="ACTIVE",
    )
    session.add(product)
    await session.commit()
    engine = TaxEngine(session, tenant.id)

    calculation = await engine.calculate(
        [
            TaxLineInput(
                key="k", product_id=product.id, category_id=product.category_id, quantity=1,
                amount=dec("2600.00"),
            )
        ],
        discount=dec("200.00"), charges=dec("0.00"), buyer_state=None,
        profile=await engine.profile(),
    )

    assert calculation.resolutions["k"].rate == dec("5.00")
    assert calculation.result.tax_amount == dec("120.00")


async def test_seeding_twice_adds_nothing_and_keeps_edits(session):
    await session.execute(
        update(GstDefaultRule)
        .where(GstDefaultRule.code == "FALLBACK_UNCLASSIFIED")
        .values(gst_rate=Decimal("12.00"))
    )
    await session.commit()

    added = await ensure_default_rules(session)

    rates = (
        await session.scalars(
            select(GstDefaultRule.gst_rate).where(GstDefaultRule.code == "FALLBACK_UNCLASSIFIED")
        )
    ).all()
    assert added == 0
    assert rates == [dec("12.00")]


async def test_the_storefront_learns_only_how_prices_are_shown(client, set_gst, tenant):
    await set_gst(state="Kerala", prices_include_gst=True)

    response = await client.get(STOREFRONT_TAX)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"gst_enabled": True, "prices_include_gst": True}
