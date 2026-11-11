"""Admin order tools: search, address correction, packing slip, label, COD remittance."""

from __future__ import annotations

import io
from datetime import date
from uuid import uuid4

import pytest
from pypdf import PdfReader

from tests.conftest import headers_for
from tests.orders.conftest import ADMIN_ORDERS, address_payload

COD = "/api/v1/admin/cod"
GST = "/api/v1/admin/gst"


def _text(response) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(response.content)).pages)


async def _search(client, headers, term):
    response = await client.get(ADMIN_ORDERS, params={"search": term}, headers=headers)
    return [o["id"] for o in response.json()["data"]]


async def test_orders_are_found_by_phone_name_product_and_number(client, admin_headers, order):
    assert await _search(client, admin_headers, order["order_number"]) == [order["id"]]
    assert await _search(client, admin_headers, "9876500001") == [order["id"]]
    assert await _search(client, admin_headers, "neha") == [order["id"]]
    assert await _search(client, admin_headers, order["items"][0]["product_name"]) == [order["id"]]
    assert await _search(client, admin_headers, order["items"][0]["sku"]) == [order["id"]]
    assert await _search(client, admin_headers, "nobody-matches-this") == []


async def test_orders_filter_by_date(client, admin_headers, order):
    today = date.today().isoformat()

    hit = await client.get(ADMIN_ORDERS, params={"start_date": today, "end_date": today}, headers=admin_headers)
    miss = await client.get(ADMIN_ORDERS, params={"start_date": "2000-01-01", "end_date": "2000-01-02"}, headers=admin_headers)

    assert len(hit.json()["data"]) == 1
    assert miss.json()["data"] == []


async def test_the_address_can_be_corrected_before_shipping(client, admin_headers, order):
    new = address_payload(address_line_1="99 New Street", city="Mysuru", postal_code="570001")
    new.pop("is_default", None)

    response = await client.patch(f"{ADMIN_ORDERS}/{order['id']}/address", json={**new, "reason": "Customer called"}, headers=admin_headers)
    tracking = (await client.get(f"{ADMIN_ORDERS}/{order['id']}/tracking", headers=admin_headers)).json()["data"]
    logs = (await client.get("/api/v1/admin/audit-logs", params={"entity_id": order["id"]}, headers=admin_headers)).json()["data"]

    assert response.status_code == 200
    assert response.json()["data"]["delivery_address"]["city"] == "Mysuru"
    assert tracking["events"][-1]["description"] == "Customer called"
    assert logs[0]["changes"]["before"]["city"] == "Bengaluru"


async def test_a_shipped_order_address_is_locked(client, admin_headers, order, set_status):
    for status in ("CONFIRMED", "PACKED", "SHIPPED"):
        await set_status(order["id"], status)
    new = address_payload(city="Mysuru")
    new.pop("is_default", None)

    response = await client.patch(f"{ADMIN_ORDERS}/{order['id']}/address", json=new, headers=admin_headers)

    assert response.status_code == 409


async def test_an_address_that_changes_gst_is_refused(client, admin_headers, customer_auth, order_in):
    await client.put(GST, json={"gstin": "29ABCDE1234F1Z5", "state": "Karnataka"}, headers=admin_headers)
    order = await order_in(customer_auth, state="Karnataka")
    moved = address_payload(state="Kerala", city="Kochi", postal_code="682001")
    moved.pop("is_default", None)

    response = await client.patch(f"{ADMIN_ORDERS}/{order['id']}/address", json=moved, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "GST_TYPE_CHANGE"


async def test_address_editing_needs_orders_manage(client, staff_headers, order):
    new = address_payload()
    new.pop("is_default", None)

    response = await client.patch(f"{ADMIN_ORDERS}/{order['id']}/address", json=new, headers=staff_headers)

    assert response.status_code == 403


async def test_the_packing_slip_lists_items_without_prices(client, staff_headers, order):
    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}/packing-slip/pdf", headers=staff_headers)

    text = _text(response)
    assert response.headers["content-type"] == "application/pdf"
    assert "PACKING SLIP" in text
    assert order["items"][0]["sku"] in text
    assert "999.00" not in text


async def test_the_shipping_label_shows_cod_to_collect(client, admin_headers, order):
    response = await client.get(f"{ADMIN_ORDERS}/{order['id']}/shipping-label/pdf", headers=admin_headers)

    text = _text(response)
    assert order["order_number"] in text
    assert "COD - collect" in text
    assert "560025" in text


async def test_slips_are_isolated_per_tenant(other_client, other_admin_headers, order):
    response = await other_client.get(f"{ADMIN_ORDERS}/{order['id']}/packing-slip/pdf", headers=other_admin_headers)

    assert response.status_code == 404


async def test_collected_cod_is_reconciled_with_a_remittance(client, admin_headers, order, set_status):
    for status in ("CONFIRMED", "PACKED", "SHIPPED", "DELIVERED"):
        await set_status(order["id"], status)

    outstanding = (await client.get(f"{COD}/collections", headers=admin_headers)).json()["data"]
    recorded = await client.post(
        f"{COD}/remittances", json={"payment_ids": [outstanding[0]["payment_id"]], "reference": "UTR123"}, headers=admin_headers
    )
    again = await client.post(
        f"{COD}/remittances", json={"payment_ids": [outstanding[0]["payment_id"]], "reference": "UTR124"}, headers=admin_headers
    )
    remitted = (await client.get(f"{COD}/collections", params={"status": "remitted"}, headers=admin_headers)).json()["data"]
    today = date.today().isoformat()
    report = (await client.get(f"{COD}/report", params={"start_date": today, "end_date": today}, headers=admin_headers)).json()["data"]

    assert [r["order_number"] for r in outstanding] == [order["order_number"]]
    assert recorded.json()["data"]["remitted"] == 1
    assert again.status_code == 409
    assert remitted[0]["remittance_reference"] == "UTR123"
    assert report["cash_remitted"] == report["cash_collected"]
    assert report["cash_outstanding"] == "0.00"


async def test_only_collected_cod_can_be_remitted(client, admin_headers, order):
    response = await client.post(
        f"{COD}/remittances", json={"payment_ids": [order["payment"]["id"]], "reference": "X"}, headers=admin_headers
    )

    assert response.status_code == 404


async def test_the_dashboard_shows_what_needs_attention(client, admin_headers, order, customer_auth, order_in, set_status):
    second = await order_in(customer_auth)
    await set_status(second["id"], "CONFIRMED")

    insights = (await client.get("/api/v1/admin/dashboard", headers=admin_headers)).json()["data"]["insights"]

    assert insights["attention"]["new_orders"] == 1
    assert insights["attention"]["awaiting_packing"] == 1
    assert insights["comparison"]["today_orders"] == 2
    assert insights["last_30_days"]["cod_orders"] == 2
    assert insights["visitors_today"] is None


async def test_the_admin_app_can_read_the_invoice_filename(client, admin_headers, order):
    from app.core.config import get_settings

    origins = get_settings().cors_origins
    if not origins:
        pytest.skip("CORS_ORIGINS is not configured")

    response = await client.get(
        f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf", headers={**admin_headers, "Origin": origins[0]}
    )

    exposed = response.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in exposed
    assert response.headers["content-disposition"].endswith(f'{order["order_number"]}.pdf"')


async def test_invoices_need_the_orders_permission(client, make_user, tenant, session, order):
    staff = await make_user(tenant=tenant, role="STAFF", email="gst-only@zeen.com")
    staff.permissions = ["settings.view"]
    await session.commit()
    headers = headers_for(staff)

    settings = await client.get(GST, headers=headers)
    invoice = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice", headers=headers)
    pdf = await client.get(f"{ADMIN_ORDERS}/{order['id']}/invoice/pdf", headers=headers)

    assert settings.status_code == 200
    assert invoice.status_code == 403
    assert pdf.status_code == 403


# ------------------------------------------------------------ bulk labels

LABELS = f"{ADMIN_ORDERS}/shipping-labels/pdf"


async def test_labels_for_several_orders_come_in_one_pdf(client, admin_headers, customer_auth, order_in, set_status):
    first = await order_in(customer_auth)
    second = await order_in(customer_auth)
    await set_status(first["id"], "CONFIRMED")
    await set_status(second["id"], "CONFIRMED")
    await set_status(second["id"], "PACKED")

    response = await client.post(LABELS, json={"order_ids": [second["id"], first["id"]]}, headers=admin_headers)

    reader = PdfReader(io.BytesIO(response.content))
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith('attachment; filename="labels-2-orders-')
    assert len(reader.pages) == 2
    assert second["order_number"] in reader.pages[0].extract_text()
    assert first["order_number"] in reader.pages[1].extract_text()


async def test_unconfirmed_or_finished_orders_get_no_label(client, admin_headers, customer_auth, order_in, set_status):
    pending = await order_in(customer_auth)
    confirmed = await order_in(customer_auth)
    await set_status(confirmed["id"], "CONFIRMED")

    response = await client.post(LABELS, json={"order_ids": [confirmed["id"], pending["id"]]}, headers=admin_headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "LABEL_NOT_ALLOWED"
    assert pending["order_number"] in response.json()["message"]


async def test_bulk_labels_are_limited_and_validated(client, admin_headers):
    too_many = await client.post(LABELS, json={"order_ids": [str(uuid4()) for _ in range(101)]}, headers=admin_headers)
    empty = await client.post(LABELS, json={"order_ids": []}, headers=admin_headers)
    unknown = await client.post(LABELS, json={"order_ids": [str(uuid4())]}, headers=admin_headers)

    assert too_many.status_code == 422
    assert empty.status_code == 422
    assert unknown.status_code == 404


async def test_bulk_labels_respect_permissions_and_stores(
    client, other_client, other_admin_headers, customer_headers, order, set_status
):
    await set_status(order["id"], "CONFIRMED")

    customer = await client.post(LABELS, json={"order_ids": [order["id"]]}, headers=customer_headers)
    other_store = await other_client.post(LABELS, json={"order_ids": [order["id"]]}, headers=other_admin_headers)

    assert customer.status_code == 403
    assert other_store.status_code == 404
