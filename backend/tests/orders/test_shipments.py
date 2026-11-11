"""Shipping through the existing checkout, stock, payment and tenant API boundaries.

All provider calls are fake. Run with backend/scripts/test.sh tests/orders/test_shipments.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.shipments.constants import ShipmentState
from app.shipments.models import ShipmentEvent
from app.shipments.provider import (
    AwbAssignment,
    BookedOrder,
    CourierRate,
    PickupResult,
    ShippingProviderError,
    TrackingScan,
    TrackingUpdate,
)

PACKAGE = {"weight_kg": "0.750", "length_cm": "25.0", "breadth_cm": "20.0", "height_cm": "4.0"}
PROVIDER = "/api/v1/admin/shipping/provider"
NOW = datetime(2026, 10, 29, 12, tzinfo=timezone.utc)


class FakeProvider:
    def __init__(self):
        self.bookings = []
        self.found = None
        self.create_error = None
        self.update = TrackingUpdate("AWB123", 1, "AWB assigned", NOW, None, None, "Courier")

    async def create_order(self, booking):
        self.bookings.append(booking)
        if self.create_error:
            raise self.create_error
        return BookedOrder("100", "200")

    async def find_order(self, reference):
        return self.found

    async def get_order(self, order_id):
        return self.found

    async def assign_awb(self, shipment_id, courier_id):
        return AwbAssignment("AWB123", "10", "Courier", Decimal("0.75"), None)

    async def check_rates(self, query):
        return [
            CourierRate(
                "10",
                "Courier",
                Decimal("40"),
                Decimal("20"),
                Decimal("60"),
                True,
                "Nov 2, 2026",
                "4",
                True,
            )
        ]

    async def schedule_pickup(self, shipment_id, pickup_date):
        return PickupResult("2026-10-30", "PICK123")

    async def generate_label(self, shipment_id):
        return "https://files.invalid/label.pdf"

    async def generate_manifest(self, shipment_id, order_id):
        return "https://files.invalid/manifest.pdf"

    async def track(self, awb_code):
        return self.update

    async def cancel_order(self, order_id):
        return None

    async def pickup_locations(self):
        return []


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr("app.shipments.service.get_client", lambda tenant_id: fake)
    monkeypatch.setattr("app.shipments.shiprocket.is_configured", lambda tenant_id=None: True)
    return fake


@pytest_asyncio.fixture(loop_scope="session")
async def shipping_order(client, admin_headers, order, provider):
    response = await client.put(
        PROVIDER,
        headers=admin_headers,
        json={
            "is_enabled": True,
            "pickup_location": "Warehouse",
            "pickup_postcode": "682001",
            "fallback_email": "orders@example.com",
            "package_defaults": PACKAGE,
        },
    )
    assert response.status_code == 200, response.text
    response = await client.patch(
        f"/api/v1/admin/orders/{order['id']}/status",
        headers=admin_headers,
        json={"status": "CONFIRMED"},
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]


def root(order):
    return f"/api/v1/admin/orders/{order['id']}/shipments"


async def book(client, headers, order, *, courier="10"):
    response = await client.post(root(order), headers=headers, json={"courier_id": courier})
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def test_creation_does_not_ship_order_and_preserves_checkout_total(
    client,
    admin_headers,
    shipping_order,
    provider,
):
    shipment = await book(client, admin_headers, shipping_order)
    assert shipment["state"] == "READY_TO_SHIP"
    assert shipment["awb_code"] == "AWB123"
    assert shipment["freight_charge"] == "40.00"
    assert len(provider.bookings) == 1
    booking = provider.bookings[0]
    assert booking.sub_total == Decimal(shipping_order["total_amount"])
    assert booking.shipping_charges == Decimal(shipping_order["shipping_amount"])
    response = await client.get(
        f"/api/v1/admin/orders/{shipping_order['id']}", headers=admin_headers
    )
    assert response.json()["data"]["status"] == "CONFIRMED"
    assert response.json()["data"]["total_amount"] == shipping_order["total_amount"]


async def test_duplicate_booking_is_refused(client, admin_headers, shipping_order, provider):
    await book(client, admin_headers, shipping_order)
    response = await client.post(root(shipping_order), headers=admin_headers, json={})
    assert response.status_code == 409
    assert len(provider.bookings) == 1


async def test_timeout_reconciliation_never_rebooks(
    client,
    admin_headers,
    shipping_order,
    provider,
):
    provider.create_error = ShippingProviderError("Timed out", retryable=True, ambiguous=True)
    response = await client.post(root(shipping_order), headers=admin_headers, json={})
    assert response.status_code == 503
    current = (await client.get(root(shipping_order), headers=admin_headers)).json()["data"][
        "current"
    ]
    assert current["operation_status"] == "UNKNOWN"
    retry = f"{root(shipping_order)}/{current['id']}/retry"
    assert (await client.post(retry, headers=admin_headers)).status_code == 503
    assert len(provider.bookings) == 1
    provider.found = BookedOrder("100", "200")
    response = await client.post(retry, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "SHIPMENT_CREATED"
    assert len(provider.bookings) == 1


async def test_explicit_refusal_can_be_retried_safely(
    client,
    admin_headers,
    shipping_order,
    provider,
):
    provider.create_error = ShippingProviderError("Fix address")
    response = await client.post(root(shipping_order), headers=admin_headers, json={})
    assert response.status_code == 409
    current = (await client.get(root(shipping_order), headers=admin_headers)).json()["data"][
        "current"
    ]
    provider.create_error = None
    response = await client.post(
        f"{root(shipping_order)}/{current['id']}/retry", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert len(provider.bookings) == 2


async def test_labels_pickups_and_manifests(client, admin_headers, shipping_order):
    shipment = await book(client, admin_headers, shipping_order)
    path = f"{root(shipping_order)}/{shipment['id']}"
    response = await client.post(f"{path}/label", headers=admin_headers)
    assert response.json()["data"]["label_url"] == "https://files.invalid/label.pdf"
    response = await client.post(f"{path}/manifest", headers=admin_headers)
    assert response.status_code == 409
    response = await client.post(f"{path}/pickup", headers=admin_headers, json={})
    assert response.json()["data"]["state"] == "PICKUP_SCHEDULED"
    response = await client.post(f"{path}/manifest", headers=admin_headers)
    assert response.json()["data"]["manifest_url"] == "https://files.invalid/manifest.pdf"


async def test_tracking_moves_order_collects_cod_and_ignores_stale_events(
    client,
    admin_headers,
    customer_auth,
    shipping_order,
    provider,
    session,
):
    shipment = await book(client, admin_headers, shipping_order)
    scan = TrackingScan(NOW, 7, "Delivered", "DLVD", "Delivered to buyer", "Kochi", {})
    provider.update = TrackingUpdate(
        "AWB123",
        7,
        "Delivered",
        NOW,
        None,
        "https://courier.invalid/track/AWB123",
        "Courier",
        [scan],
    )
    path = f"{root(shipping_order)}/{shipment['id']}/sync"
    response = await client.post(path, headers=admin_headers)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == "DELIVERED"
    response = await client.get(f"/api/v1/orders/{shipping_order['id']}", headers=customer_auth)
    assert response.json()["data"]["status"] == "DELIVERED"
    assert response.json()["data"]["payment_status"] == "PAID"
    await client.post(path, headers=admin_headers)
    events = (
        await session.scalars(
            select(ShipmentEvent).where(ShipmentEvent.shipment_id == UUID(shipment["id"]))
        )
    ).all()
    assert len(events) == 2  # one scan and one headline; neither repeated
    provider.update = TrackingUpdate("AWB123", 18, "In transit", NOW, None, None, None)
    response = await client.post(path, headers=admin_headers)
    assert response.json()["data"]["state"] == "DELIVERED"


async def test_customer_tracking_omits_store_costs_and_internal_errors(
    client,
    admin_headers,
    customer_auth,
    shipping_order,
):
    await book(client, admin_headers, shipping_order)
    response = await client.get(
        f"/api/v1/orders/{shipping_order['id']}/tracking", headers=customer_auth
    )
    courier = response.json()["data"]["courier"]
    assert courier["awb_code"] == "AWB123"
    assert "cod_amount" not in courier
    assert "freight_charge" not in courier
    assert "last_error" not in courier


async def test_cancellation_preserves_order_and_new_attempt_has_new_reference(
    client,
    admin_headers,
    shipping_order,
    provider,
):
    first = await book(client, admin_headers, shipping_order)
    response = await client.post(
        f"{root(shipping_order)}/{first['id']}/cancel", headers=admin_headers
    )
    assert response.json()["data"]["state"] == "CANCELLED"
    second = await book(client, admin_headers, shipping_order, courier=None)
    assert second["channel_order_id"] != first["channel_order_id"]
    assert second["attempt"] == 2
    response = await client.get(
        f"/api/v1/admin/orders/{shipping_order['id']}", headers=admin_headers
    )
    assert response.json()["data"]["status"] == "CONFIRMED"


async def test_order_cannot_be_cancelled_while_courier_booking_is_active(
    client,
    admin_headers,
    shipping_order,
):
    await book(client, admin_headers, shipping_order)
    response = await client.patch(
        f"/api/v1/admin/orders/{shipping_order['id']}/status",
        headers=admin_headers,
        json={"status": "CANCELLED"},
    )
    assert response.status_code == 409


async def test_tenant_and_customer_cannot_access_admin_shipments(
    client,
    other_client,
    admin_headers,
    other_admin_headers,
    customer_auth,
    shipping_order,
):
    await book(client, admin_headers, shipping_order)
    assert (await client.get(root(shipping_order), headers=customer_auth)).status_code == 403
    assert (
        await client.post(root(shipping_order), headers=customer_auth, json={})
    ).status_code == 403
    assert (
        await other_client.get(root(shipping_order), headers=other_admin_headers)
    ).status_code == 404


async def test_unpaid_online_order_is_not_shippable(client, admin_headers, shipping_order, session):
    from app.orders.models import Order

    order = await session.get(Order, UUID(shipping_order["id"]))
    order.payment_method = "UPI"
    await session.commit()
    response = await client.post(root(shipping_order), headers=admin_headers, json={})
    assert response.status_code == 409


async def test_return_to_origin_does_not_collect_cod(
    client,
    admin_headers,
    customer_auth,
    shipping_order,
    provider,
):
    shipment = await book(client, admin_headers, shipping_order)
    provider.update = TrackingUpdate("AWB123", 10, "RTO Delivered", NOW, None, None, None)
    response = await client.post(
        f"{root(shipping_order)}/{shipment['id']}/sync", headers=admin_headers
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["state"] == ShipmentState.RETURNED_TO_ORIGIN.value
    response = await client.get(f"/api/v1/orders/{shipping_order['id']}", headers=customer_auth)
    assert response.json()["data"]["status"] == "RETURNED"
    assert response.json()["data"]["payment_status"] != "PAID"
