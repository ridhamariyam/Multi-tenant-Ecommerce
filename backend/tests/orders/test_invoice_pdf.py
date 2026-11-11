"""Downloading the GST invoice as a PDF."""

from __future__ import annotations

import io
from decimal import Decimal

from pypdf import PdfReader

from tests.conftest import headers_for
from tests.orders.conftest import ADMIN_ORDERS, CUSTOMERS, ORDERS

GST = "/api/v1/admin/gst"
COD = "/api/v1/admin/cod/settings"
UNKNOWN_ID = "00000000-0000-0000-0000-000000000000"


def _text(response) -> str:
    reader = PdfReader(io.BytesIO(response.content))
    return "\n".join(page.extract_text() for page in reader.pages)


async def _gst(client, headers, **overrides):
    response = await client.put(
        GST,
        json={
            "gstin": "29ABCDE1234F1Z5",
            "legal_name": "Zeen Fashions Pvt Ltd",
            "address": "1 MG Road, Bengaluru",
            "state": "Karnataka",
            "registration_status": "REGISTERED",
            "shipping_sac_code": "996812",
            **overrides,
        },
        headers=headers,
    )
    assert response.status_code == 200, response.text
    response = await client.post(f"{GST}/activate", json={"ca_confirmed": True}, headers=headers)
    assert response.status_code == 200, response.text


async def test_a_customer_downloads_their_invoice(client, admin_headers, customer_auth, order_in):
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Karnataka")

    response = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == (
        f'attachment; filename="INV-{order["order_number"]}.pdf"'
    )
    assert response.content.startswith(b"%PDF-")


async def test_the_pdf_carries_the_json_invoice_figures(
    client, admin_headers, customer_auth, order_in
):
    await _gst(client, admin_headers)
    await client.put(COD, json={"fee_amount": "50.00"}, headers=admin_headers)
    order = await order_in(customer_auth, state="Karnataka")
    invoice = (
        await client.get(f"{ORDERS}/{order['id']}/invoice", headers=customer_auth)
    ).json()["data"]

    text = _text(await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth))

    for expected in (
        "TAX INVOICE",
        "Zeen",
        "Zeen Fashions Pvt Ltd",
        "GSTIN: 29ABCDE1234F1Z5",
        invoice["invoice_number"],
        order["order_number"],
        "Neha Kapoor",
        "560025",
        "+919876500001",
        order["items"][0]["sku"],
        "CGST",
        "SGST",
        "COD charges",
        f"{Decimal(invoice['totals']['cgst_amount']):,.2f}",
        f"{Decimal(invoice['totals']['total']):,.2f}",
        f"{Decimal(invoice['totals']['cod_fee']):,.2f}",
    ):
        assert expected in text, expected


async def test_an_inter_state_invoice_shows_igst(client, admin_headers, customer_auth, order_in):
    await _gst(client, admin_headers)
    order = await order_in(customer_auth, state="Kerala", postal_code="682001")

    text = _text(await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth))

    assert "IGST" in text
    assert "Inter-state" in text


async def test_an_invoice_without_gst_settings_still_renders(client, customer_auth, order):
    response = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth)

    assert response.status_code == 200
    assert order["order_number"] in _text(response)


async def test_staff_download_any_invoice_in_their_tenant(client, staff_headers, order):
    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf", headers=staff_headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"


async def test_the_json_invoice_still_works(client, customer_auth, order):
    response = await client.get(f"{ORDERS}/{order['id']}/invoice", headers=customer_auth)

    assert response.status_code == 200
    assert response.json()["data"]["order_number"] == order["order_number"]


async def test_another_customers_invoice_is_not_found(client, make_user, tenant, order):
    stranger = headers_for(await make_user(tenant=tenant, phone=CUSTOMERS["intruder"]))

    response = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=stranger)

    assert response.status_code == 404


async def test_the_customer_route_needs_a_customer(client, staff_headers, order):
    response = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=staff_headers)

    assert response.status_code == 403


async def test_the_admin_route_refuses_customers(client, customer_auth, order):
    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth)

    assert response.status_code == 403


async def test_downloading_needs_authentication(client, order):
    customer = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf")
    admin = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf")

    assert customer.status_code == 401
    assert admin.status_code == 401


async def test_another_tenants_admin_cannot_download(
    other_client, other_admin_headers, order
):
    response = await other_client.get(
        f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf", headers=other_admin_headers
    )

    assert response.status_code == 404


async def test_a_token_from_one_tenant_is_refused_on_another(
    other_client, other_tenant, customer_auth, order
):
    response = await other_client.get(
        f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth
    )

    assert response.status_code == 401


async def test_an_unknown_order_is_not_found(client, admin_headers, customer_auth, tenant):
    customer = await client.get(f"{ORDERS}/{UNKNOWN_ID}/invoice/pdf", headers=customer_auth)
    admin = await client.get(f"{ADMIN_ORDERS}/{UNKNOWN_ID}/invoice/pdf", headers=admin_headers)

    assert customer.status_code == 404
    assert admin.status_code == 404


async def test_a_malformed_order_id_is_rejected(client, admin_headers):
    response = await client.get(f"{ADMIN_ORDERS}/not-a-uuid/invoice/pdf", headers=admin_headers)

    assert response.status_code == 422


async def test_an_unsafe_invoice_prefix_makes_a_safe_filename(
    client, admin_headers, customer_auth, order_in
):
    # The prefix is frozen onto the order at checkout, so it is set first.
    await _gst(client, admin_headers, invoice_prefix='ZN/2026"')
    order = await order_in(customer_auth)

    response = await client.get(f"{ORDERS}/{order['id']}/invoice/pdf", headers=customer_auth)

    assert response.headers["content-disposition"] == (
        f'attachment; filename="ZN-2026-{order["order_number"]}.pdf"'
    )
