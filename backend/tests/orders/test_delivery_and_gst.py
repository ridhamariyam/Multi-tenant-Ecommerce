"""Pincode serviceability, delivery estimates, shipping cost, GST split and invoices."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import update

from app.orders.models import OrderItem
from tests.catalogue.factories import PRODUCTS, make_category, make_product
from tests.orders.conftest import ADMIN_ORDERS, CHECKOUT, ORDERS

API = "/api/v1"
PINCODES = f"{API}/admin/pincodes"
DELIVERY = f"{API}/storefront/delivery/check"
SHIPPING = f"{API}/admin/shipping"
TAX = f"{API}/admin/tax"
GST = f"{API}/admin/gst"


async def _shipping(client, headers, **overrides):
    payload = {"shipping_amount": "100.00", "free_shipping_minimum": "5000.00", **overrides}
    response = await client.put(SHIPPING, json=payload, headers=headers)
    assert response.status_code == 200, response.text


async def _tax(client, headers, tax_ready, rate="18.00"):
    """Set and CA-confirm the charges rate, and map goods without a rate of their own to it."""
    response = await client.put(TAX, json={"tax_percentage": rate}, headers=headers)
    assert response.status_code == 200, response.text
    response = await client.post(f"{TAX}/confirm", json={"ca_confirmed": True}, headers=headers)
    assert response.status_code == 200, response.text
    await tax_ready.use_default_rate(rate)


async def _gst(client, headers, **overrides):
    """Save the seller's GST details and, if they are accepted, activate them."""
    payload = {
        "gstin": "29ABCDE1234F1Z5",
        "legal_name": "Zeen Fashions Pvt Ltd",
        "address": "1 MG Road, Bengaluru",
        "state": "Karnataka",
        "registration_status": "REGISTERED",
        "shipping_sac_code": "996812",
        **overrides,
    }
    saved = await client.put(GST, json=payload, headers=headers)
    if saved.status_code != 200:
        return saved
    activated = await client.post(f"{GST}/activate", json={"ca_confirmed": True}, headers=headers)
    assert activated.status_code == 200, activated.text
    return activated


# ------------------------------------------------------------------ delivery


async def test_an_unlisted_pincode_is_served_by_default(client, admin_headers):
    await _shipping(client, admin_headers, min_delivery_days=2, max_delivery_days=5)

    response = await client.get(DELIVERY, params={"pincode": "682001"})

    body = response.json()["data"]
    assert body["serviceable"] is True
    assert body["min_delivery_days"] == 2
    assert date.fromisoformat(body["estimated_delivery_date"]) >= date.today() + timedelta(days=4)
    assert Decimal(body["shipping_amount"]) == Decimal("100.00")
    assert body["cod_available"] is True


async def test_a_blocked_pincode_is_not_served(client, admin_headers):
    await client.put(f"{PINCODES}/110001", json={"is_serviceable": False}, headers=admin_headers)

    response = await client.get(DELIVERY, params={"pincode": "110001"})

    body = response.json()["data"]
    assert body["serviceable"] is False
    assert body["estimated_delivery_date"] is None
    assert body["cod_available"] is False


async def test_listed_only_mode_serves_only_listed_pincodes(client, admin_headers):
    await _shipping(client, admin_headers, restrict_to_listed_pincodes=True)
    await client.put(f"{PINCODES}/682001", json={}, headers=admin_headers)

    listed = await client.get(DELIVERY, params={"pincode": "682001"})
    unlisted = await client.get(DELIVERY, params={"pincode": "560001"})

    assert listed.json()["data"]["serviceable"] is True
    assert unlisted.json()["data"]["serviceable"] is False


async def test_a_pincode_overrides_days_charge_and_cod(client, admin_headers):
    await _shipping(client, admin_headers)
    await client.put(
        f"{PINCODES}/793001",
        json={
            "min_delivery_days": 8,
            "max_delivery_days": 12,
            "shipping_amount": "250.00",
            "cod_available": False,
        },
        headers=admin_headers,
    )

    body = (await client.get(DELIVERY, params={"pincode": "793001"})).json()["data"]

    assert body["max_delivery_days"] == 12
    assert Decimal(body["shipping_amount"]) == Decimal("250.00")
    assert body["cod_available"] is False


async def test_the_free_shipping_threshold_still_applies(client, admin_headers):
    await _shipping(client, admin_headers, free_shipping_minimum="1000.00")
    await client.put(f"{PINCODES}/793001", json={"shipping_amount": "250.00"}, headers=admin_headers)

    body = (
        await client.get(DELIVERY, params={"pincode": "793001", "subtotal": "1500.00"})
    ).json()["data"]

    assert Decimal(body["shipping_amount"]) == Decimal("0.00")


async def test_an_invalid_pincode_is_rejected(client, tenant):
    response = await client.get(DELIVERY, params={"pincode": "012345"})

    assert response.status_code == 422


async def test_admins_manage_pincode_rules(client, admin_headers, staff_headers):
    bulk = await client.post(
        f"{PINCODES}/bulk",
        json={"rules": [{"pincode": "682001"}, {"pincode": "682002", "cod_available": False}]},
        headers=admin_headers,
    )
    listed = await client.get(PINCODES, params={"search": "6820"}, headers=staff_headers)
    staff_write = await client.put(f"{PINCODES}/682003", json={}, headers=staff_headers)
    deleted = await client.delete(f"{PINCODES}/682001", headers=admin_headers)
    gone = await client.get(f"{PINCODES}/682001", headers=admin_headers)

    assert bulk.json()["data"] == {"saved": 2}
    assert [r["pincode"] for r in listed.json()["data"]] == ["682001", "682002"]
    assert staff_write.status_code == 403
    assert deleted.status_code == 204
    assert gone.status_code == 404


async def test_pincode_days_must_come_in_pairs(client, admin_headers):
    response = await client.put(
        f"{PINCODES}/682001", json={"min_delivery_days": 3}, headers=admin_headers
    )

    assert response.status_code == 422


async def test_checkout_refuses_an_unserviceable_pincode(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await client.put(f"{PINCODES}/560025", json={"is_serviceable": False}, headers=admin_headers)
    address = await save_address(customer_auth)
    await add_to_cart(customer_auth, variant["id"], 1)

    preview = await client.post(
        f"{CHECKOUT}/preview", json={"address_id": address["id"]}, headers=customer_auth
    )
    response = await place_order(customer_auth, address["id"])

    assert preview.json()["data"]["delivery"]["serviceable"] is False
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "PINCODE_NOT_SERVICEABLE"


async def test_the_order_carries_the_estimate_and_pincode_charge(
    client, admin_headers, customer_auth, variant, add_to_cart, save_address, place_order
):
    await _shipping(client, admin_headers)
    await client.put(
        f"{PINCODES}/560025",
        json={"min_delivery_days": 1, "max_delivery_days": 2, "shipping_amount": "40.00"},
        headers=admin_headers,
    )
    address = await save_address(customer_auth)
    await add_to_cart(customer_auth, variant["id"], 1)

    order = (await place_order(customer_auth, address["id"])).json()["data"]

    assert Decimal(order["shipping_amount"]) == Decimal("40.00")
    assert order["estimated_delivery_date"] == (date.today() + timedelta(days=2)).isoformat()


# ----------------------------------------------------------------------- GST


async def test_gst_settings_resolve_the_state_code(client, admin_headers):
    response = await _gst(client, admin_headers)

    body = response.json()["data"]
    assert body["state"] == "Karnataka"
    assert body["state_code"] == "29"


async def test_a_gstin_from_another_state_is_rejected(client, admin_headers):
    response = await _gst(client, admin_headers, state="Kerala")

    assert response.status_code == 400


async def test_a_malformed_gstin_is_rejected(client, admin_headers):
    response = await _gst(client, admin_headers, gstin="NOT-A-GSTIN")

    assert response.status_code == 422


async def test_an_intra_state_order_splits_cgst_and_sgst(
    client, admin_headers, customer_auth, order_in
):
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Karnataka")

    assert order["gst"]["gst_type"] == "INTRA_STATE"
    assert Decimal(order["gst"]["cgst_amount"]) + Decimal(order["gst"]["sgst_amount"]) == Decimal(
        order["tax_amount"]
    )
    assert Decimal(order["gst"]["igst_amount"]) == Decimal("0.00")
    assert order["gst"]["place_of_supply"] == "Karnataka (29)"


async def test_an_inter_state_order_charges_igst(client, admin_headers, customer_auth, order_in):
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Kerala", postal_code="682001")

    assert order["gst"]["gst_type"] == "INTER_STATE"
    assert Decimal(order["gst"]["igst_amount"]) == Decimal(order["tax_amount"])
    assert Decimal(order["gst"]["cgst_amount"]) == Decimal("0.00")


async def test_a_product_rate_and_hsn_override_the_default(
    client, admin_headers, customer_auth, add_to_cart, save_address, place_order, tax_ready
):
    await _tax(client, admin_headers, tax_ready, "18.00")
    category = await make_category(
        client, admin_headers, name="Churidars", hsn_code="6204", gst_rate="5.00"
    )
    product = await make_product(client, admin_headers, category["id"], status="ACTIVE")
    variant = (
        await client.post(
            f"{PRODUCTS}/{product['id']}/variants",
            json={"sku": "GST-5", "name": "S", "price": "1000.00", "status": "ACTIVE", "initial_quantity": 5},
            headers=admin_headers,
        )
    ).json()["data"]
    address = await save_address(customer_auth)
    await add_to_cart(customer_auth, variant["id"], 2)

    order = (await place_order(customer_auth, address["id"])).json()["data"]

    item = order["items"][0]
    assert item["hsn_code"] == "6204"
    assert Decimal(item["gst_rate"]) == Decimal("5.00")
    assert Decimal(item["tax_amount"]) == Decimal("100.00")
    assert Decimal(order["tax_amount"]) == Decimal("100.00")


async def test_the_invoice_has_gst_lines_and_seller_details(
    client, admin_headers, customer_auth, order_in
):
    await _gst(client, admin_headers, invoice_prefix="ZN/")
    order = await order_in(customer_auth, state="Karnataka")

    response = await client.get(f"{ORDERS}/{order['id']}/invoice", headers=customer_auth)
    admin = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice", headers=admin_headers)
    retry = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice", headers=admin_headers)

    invoice = response.json()["data"]
    assert response.status_code == 200
    assert admin.status_code == 200
    assert retry.json()["data"]["invoice_number"] == admin.json()["data"]["invoice_number"]
    assert invoice["invoice_number"] == f"ZN/{order['order_number']}"
    assert invoice["seller"]["gstin"] == "29ABCDE1234F1Z5"
    assert invoice["gst_type"] == "INTRA_STATE"
    lines_tax = sum(
        Decimal(line["cgst_amount"]) + Decimal(line["sgst_amount"]) + Decimal(line["igst_amount"])
        for line in invoice["lines"]
    )
    assert lines_tax == Decimal(order["tax_amount"])
    assert Decimal(invoice["totals"]["total"]) == Decimal(order["total_amount"])


async def test_invoice_numbers_are_distinct_and_stable_on_read_retries(
    client, admin_headers, customer_auth, order_in
):
    await _gst(client, admin_headers, invoice_prefix="ZN/")
    first = await order_in(customer_auth, state="Karnataka")
    second = await order_in(customer_auth, state="Karnataka")
    first_endpoint = f"{ADMIN_ORDERS}/{first['id']}/invoice"
    second_endpoint = f"{ADMIN_ORDERS}/{second['id']}/invoice"
    first_number = (await client.get(first_endpoint, headers=admin_headers)).json()["data"]["invoice_number"]
    retry_number = (await client.get(first_endpoint, headers=admin_headers)).json()["data"]["invoice_number"]
    second_number = (await client.get(second_endpoint, headers=admin_headers)).json()["data"]["invoice_number"]
    assert first_number == retry_number
    assert first_number != second_number


async def test_someone_elses_invoice_is_not_found(
    client, make_user, tenant, customer_auth, order_in
):
    from tests.conftest import headers_for

    order = await order_in(customer_auth)
    stranger = headers_for(await make_user(tenant=tenant, phone="+919822229999"))

    response = await client.get(f"{ORDERS}/{order['id']}/invoice", headers=stranger)

    assert response.status_code == 404


async def test_the_gst_report_totals_orders_by_rate(client, admin_headers, customer_auth, order_in):
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Karnataka")
    today = date.today().isoformat()

    response = await client.get(
        f"{GST}/report", params={"start_date": today, "end_date": today}, headers=admin_headers
    )

    report = response.json()["data"]
    assert report["order_count"] == 1
    assert Decimal(report["tax_amount"]) == Decimal(order["tax_amount"])
    assert Decimal(report["cgst_amount"]) + Decimal(report["sgst_amount"]) == Decimal(
        order["tax_amount"]
    )
    assert report["by_rate"][0]["gst_type"] == "INTRA_STATE"
    for field in ("taxable_amount", "cgst_amount", "sgst_amount", "igst_amount"):
        assert sum(Decimal(row[field]) for row in report["by_rate"]) == Decimal(report[field])


async def test_gst_report_reconciles_shipping_and_legacy_item_tax(
    client, admin_headers, customer_auth, order_in, session, tax_ready
):
    await _shipping(client, admin_headers)
    await _tax(client, admin_headers, tax_ready)
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Karnataka")
    await session.execute(
        update(OrderItem)
        .where(OrderItem.order_id == UUID(order["id"]))
        .values(taxable_amount=None, tax_amount=None)
    )
    await session.commit()
    today = date.today().isoformat()
    response = await client.get(
        f"{GST}/report", params={"start_date": today, "end_date": today}, headers=admin_headers
    )
    assert response.status_code == 200, response.text
    report = response.json()["data"]
    assert report["order_count"] == 1
    assert any(row["component"] == "CHARGES_AND_ADJUSTMENTS" for row in report["by_rate"])
    for field in ("taxable_amount", "cgst_amount", "sgst_amount", "igst_amount"):
        assert sum(Decimal(row[field]) for row in report["by_rate"]) == Decimal(report[field])
    assert Decimal(report["tax_amount"]) == Decimal(order["tax_amount"])


async def test_preview_without_an_address_has_no_gst_split(
    client, admin_headers, customer_auth, variant, add_to_cart, tax_ready
):
    await _tax(client, admin_headers, tax_ready)
    await add_to_cart(customer_auth, variant["id"], 1)

    body = (await client.post(f"{CHECKOUT}/preview", headers=customer_auth)).json()["data"]

    assert body["gst"] is None
    assert Decimal(body["tax_amount"]) > 0

