"""Google Sheets order export: which orders are sales, written once, per store."""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.integrations import google_sheets, order_sheets
from app.integrations.google_sheets import SheetsError
from app.integrations.models import OrderSheetExport
from app.integrations.order_sheets import HEADER, OrderSheetService
from app.orders.models import Order
from tests.orders.conftest import CART, CHECKOUT, address_payload

SETTINGS = "/api/v1/admin/integrations/google-sheets"
SHEET_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=0"
OTHER_SHEET_ID = "1ZyXwVuTsRqPoNmLkJiHgFeDcBa9876543210"


class FakeSheets:
    """Stands in for Google: one dict of tabs per spreadsheet."""

    def __init__(self) -> None:
        self.books: dict[str, dict[str, list[list]]] = {}
        self.fail: SheetsError | None = None

    def client(self, spreadsheet_id: str):
        fake = self

        class Client:
            def __init__(self, _id: str) -> None:
                self.spreadsheet_id = _id

            async def ensure_worksheet(self, title, header):
                if fake.fail:
                    raise fake.fail
                tab = fake.books.setdefault(self.spreadsheet_id, {}).setdefault(title, [])
                if not tab:
                    tab.append(list(header))

            async def append_rows(self, title, rows):
                if fake.fail:
                    raise fake.fail
                fake.books[self.spreadsheet_id][title].extend(rows)

        return Client(spreadsheet_id)

    def rows(self, spreadsheet_id=SHEET_ID, tab="Orders") -> list[list]:
        return self.books.get(spreadsheet_id, {}).get(tab, [])[1:]


@pytest.fixture
def sheets(monkeypatch) -> FakeSheets:
    fake = FakeSheets()
    monkeypatch.setattr(order_sheets, "SheetsClient", fake.client)
    monkeypatch.setattr(google_sheets, "is_configured", lambda: True)
    monkeypatch.setattr(
        google_sheets, "service_account_email", lambda: "orders@cliq-sheets.iam.gserviceaccount.com"
    )
    return fake


@pytest_asyncio.fixture(loop_scope="session")
async def connect(client, admin_headers, sheets):
    async def _connect(spreadsheet=SHEET_URL, enabled=True, expect=200):
        response = await client.put(
            SETTINGS,
            json={"is_enabled": enabled, "spreadsheet": spreadsheet, "worksheet_name": "Orders"},
            headers=admin_headers,
        )
        assert response.status_code == expect, response.text
        return response.json()

    return _connect


async def _guest_order(client, variant_id, quantity=1, phone="9833330001", **address) -> dict:
    cart = (await client.post(f"{CART}/guest")).json()["data"]
    headers = {"X-Cart-Token": cart["guest_token"]}
    added = await client.post(
        f"{CART}/items", json={"variant_id": variant_id, "quantity": quantity}, headers=headers
    )
    assert added.status_code == 201, added.text
    response = await client.post(
        f"{CHECKOUT}/guest",
        json={
            "contact": {"name": "Asha Guest", "phone": phone, "email": "asha@example.com"},
            "address": address_payload(**address),
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _sync(client, admin_headers) -> dict:
    response = await client.post(f"{SETTINGS}/sync", headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()["data"]


async def test_connecting_writes_the_header_and_shows_the_share_address(connect, sheets):
    body = await connect()

    data = body["data"]
    assert data["is_enabled"] is True
    assert data["spreadsheet_id"] == SHEET_ID
    assert data["spreadsheet_url"] == f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    assert data["service_account_email"] == "orders@cliq-sheets.iam.gserviceaccount.com"
    assert sheets.books[SHEET_ID]["Orders"] == [HEADER]


async def test_a_cod_order_is_written_once_with_its_numbers(
    client, admin_headers, connect, sheets, variant
):
    await connect()
    placed = await _guest_order(client, variant["id"], 2)

    first = await _sync(client, admin_headers)
    second = await _sync(client, admin_headers)

    assert first == {"exported": 1, "pending": 0, "error": None}
    assert second["exported"] == 0
    rows = sheets.rows()
    assert len(rows) == 1
    row = dict(zip(HEADER, rows[0]))
    assert row["Order Number"] == placed["order_number"]
    assert row["Payment Method"] == "Cash on delivery"
    assert row["Deliver To"] == placed["delivery_address"]["full_name"]
    assert row["Delivery Phone"] == placed["delivery_address"]["phone"]
    assert row["Email"] == "asha@example.com"
    assert row["Quantity"] == 2
    assert row["Guest Checkout"] == "Yes"
    assert Decimal(str(row["Subtotal"])) == Decimal(placed["subtotal"])
    assert Decimal(str(row["Total"])) == Decimal(placed["total_amount"])
    assert " x 2" in row["Items"]


async def test_an_unpaid_online_order_waits_until_it_is_paid(
    client, session, admin_headers, connect, sheets, variant
):
    await connect()
    placed = await _guest_order(client, variant["id"])
    order = await session.get(Order, UUID(placed["id"]))
    order.payment_method = "UPI"
    order.payment_status = "PENDING"
    await session.commit()

    assert (await _sync(client, admin_headers))["exported"] == 0

    order.payment_status = "PAID"
    await session.commit()
    assert (await _sync(client, admin_headers))["exported"] == 1
    assert dict(zip(HEADER, sheets.rows()[0]))["Payment Method"] == "UPI"


async def test_a_cancelled_order_is_not_a_sale(
    client, session, admin_headers, connect, sheets, variant
):
    await connect()
    placed = await _guest_order(client, variant["id"])
    order = await session.get(Order, UUID(placed["id"]))
    order.status = "CANCELLED"
    await session.commit()

    assert (await _sync(client, admin_headers))["exported"] == 0
    assert sheets.rows() == []


async def test_nothing_is_written_while_the_export_is_off(
    client, admin_headers, connect, sheets, variant
):
    await connect(enabled=False)
    await _guest_order(client, variant["id"])

    assert (await _sync(client, admin_headers))["exported"] == 0
    assert sheets.rows() == []


async def test_a_google_failure_is_recorded_and_retried_next_run(
    client, session, admin_headers, connect, sheets, variant
):
    await connect()
    await _guest_order(client, variant["id"])
    sheets.fail = SheetsError("Could not reach Google Sheets. Try again shortly.")

    failed = await _sync(client, admin_headers)
    shown = (await client.get(SETTINGS, headers=admin_headers)).json()["data"]

    assert failed["exported"] == 0
    assert failed["error"] == "Could not reach Google Sheets. Try again shortly."
    assert shown["last_error"] == failed["error"]
    assert shown["pending_orders"] == 1
    assert (await session.scalars(select(OrderSheetExport))).all() == []

    sheets.fail = None
    retried = await _sync(client, admin_headers)
    assert retried == {"exported": 1, "pending": 0, "error": None}
    shown = (await client.get(SETTINGS, headers=admin_headers)).json()["data"]
    assert shown["last_error"] is None
    assert shown["exported_orders"] == 1


async def test_a_new_spreadsheet_gets_every_sale_too(
    client, admin_headers, connect, sheets, variant
):
    await connect()
    await _guest_order(client, variant["id"])
    await _sync(client, admin_headers)

    await connect(spreadsheet=OTHER_SHEET_ID)
    await _sync(client, admin_headers)

    assert len(sheets.rows()) == 1
    assert len(sheets.rows(OTHER_SHEET_ID)) == 1


async def test_only_this_stores_orders_reach_its_sheet(
    client, session, other_tenant, admin_headers, connect, sheets, variant
):
    await connect()
    await _guest_order(client, variant["id"])
    placed = (await session.scalars(select(Order))).one()

    exported = await OrderSheetService(session, other_tenant.id).sync()

    assert exported.exported == 0
    assert placed.tenant_id != other_tenant.id
    assert sheets.rows() == []


async def test_no_access_is_reported_on_the_spreadsheet_field(connect, sheets):
    sheets.fail = SheetsError(
        "No access to this spreadsheet. Share it with x@y as an Editor.", kind="access_denied"
    )

    body = await connect(expect=400)

    assert body["error"]["code"] == "SHEETS_ACCESS_DENIED"
    assert body["error"]["details"][0]["field"] == "spreadsheet"


async def test_a_link_that_is_not_a_sheet_is_refused(connect):
    body = await connect(spreadsheet="https://example.com/not-a-sheet", expect=400)

    assert body["error"]["code"] == "SHEETS_INVALID_SPREADSHEET"


async def test_staff_without_settings_access_cannot_connect(client, staff_headers, sheets):
    response = await client.put(
        SETTINGS, json={"is_enabled": False, "spreadsheet": SHEET_ID}, headers=staff_headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------- the HTTP client


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (SHEET_URL, SHEET_ID),
        (f"  {SHEET_ID}  ", SHEET_ID),
        ("https://docs.google.com/spreadsheets/u/0/", None),
        ("not a sheet", None),
    ],
)
def test_spreadsheet_ids_are_read_from_links_or_ids(value, expected):
    assert google_sheets.parse_spreadsheet_id(value) == expected


async def test_the_client_appends_raw_values_to_the_quoted_tab(monkeypatch):
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.method == "GET" and request.url.path.endswith(SHEET_ID):
            return httpx.Response(200, json={"sheets": [{"properties": {"title": "Bob's Orders"}}]})
        if request.method == "GET":
            return httpx.Response(200, json={"values": [["Order Number"]]})
        return httpx.Response(200, json={})

    real_client = httpx.AsyncClient

    async def token():
        return "test-token"

    monkeypatch.setattr(google_sheets, "_access_token", token)
    monkeypatch.setattr(
        google_sheets.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )

    client = google_sheets.SheetsClient(SHEET_ID)
    await client.ensure_worksheet("Bob's Orders", HEADER)
    await client.append_rows("Bob's Orders", [["=HYPERLINK(\"x\")", 1.5]])

    append = calls[-1]
    assert append.method == "POST"
    assert append.headers["Authorization"] == "Bearer test-token"
    assert append.url.params["valueInputOption"] == "RAW"
    assert "%27Bob%27%27s%20Orders%27%21A1:append" in str(append.url)
    assert len(calls) == 3  # tab exists and has a header: nothing created or rewritten


async def test_the_client_explains_a_permission_error(monkeypatch):
    real_client = httpx.AsyncClient

    async def token():
        return "test-token"

    monkeypatch.setattr(google_sheets, "_access_token", token)
    monkeypatch.setattr(google_sheets, "service_account_email", lambda: "svc@example.iam")
    monkeypatch.setattr(
        google_sheets.httpx,
        "AsyncClient",
        lambda **kwargs: real_client(
            transport=httpx.MockTransport(lambda request: httpx.Response(403)), **kwargs
        ),
    )

    with pytest.raises(SheetsError) as raised:
        await google_sheets.SheetsClient(SHEET_ID).append_rows("Orders", [["x"]])

    assert raised.value.kind == "access_denied"
    assert "svc@example.iam" in raised.value.message
