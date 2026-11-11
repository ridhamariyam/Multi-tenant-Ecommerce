"""Provider and recovery checks runnable without PostgreSQL or real courier calls.

Run: python -m unittest tests.shipments.test_unit -v
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx

from app.core.exceptions import AuthenticationError, ConflictError, ServiceUnavailableError
from app.orders.constants import ALLOWED_TRANSITIONS, OrderStatus
from app.shipments import router, shiprocket
from app.shipments.constants import ShipmentOperation, ShipmentState
from app.shipments.provider import (
    BookedOrder,
    BookingItem,
    BookingRequest,
    Package,
    ProviderNotConfiguredError,
    RateQuery,
    ShippingProviderError,
    TrackingUpdate,
)
from app.shipments.schemas import PackageInput, ProviderSettingsUpdate
from app.shipments.service import ShipmentService, can_move, order_path

PARCEL = Package(Decimal("0.750"), Decimal("25"), Decimal("20"), Decimal("4"))
CREDS = shiprocket.Credentials(
    "api@example.com", "test-only", "https://courier.invalid/v1/external", 1, 3600, 2
)
AT = datetime(2026, 10, 29, 10, tzinfo=timezone.utc)


def booking(**overrides):
    values = dict(
        channel_order_id="12345-1",
        order_date=AT,
        pickup_location="Warehouse",
        customer_name="Test Buyer",
        address_line_1="Main Road",
        address_line_2=None,
        city="Kochi",
        state="Kerala",
        postcode="682001",
        country="India",
        email="buyer@example.com",
        phone="+919876543210",
        items=[
            BookingItem("Kurta", "KURTA-1", 1, Decimal("1000"), Decimal("0"), Decimal("5"), "6204")
        ],
        cod=True,
        shipping_charges=Decimal("50"),
        transaction_charges=Decimal("20"),
        total_discount=Decimal("100"),
        sub_total=Decimal("970"),
        package=PARCEL,
    )
    return BookingRequest(**(values | overrides))


def shipment(**overrides):
    values = dict(
        id=uuid4(),
        tenant_id=uuid4(),
        order_id=uuid4(),
        channel_order_id="12345-1",
        state="READY_TO_SHIP",
        provider_order_id="100",
        provider_shipment_id="200",
        awb_code="AWB123",
        courier_name=None,
        pending_operation=None,
        operation_status=None,
        updated_at=AT,
        last_event_at=None,
        provider_status_code=None,
        provider_status_label=None,
        picked_up_at=None,
        delivered_at=None,
        cancelled_at=None,
        next_sync_at=None,
        last_error=None,
        retry_count=0,
    )
    return SimpleNamespace(**(values | overrides))


class MemoryCache:
    def __init__(self):
        self.data = {}

    async def get(self, key):
        return self.data.get(key)

    async def set(self, key, value, **kwargs):
        self.data[key] = value

    async def delete(self, key):
        self.data.pop(key, None)


class ProviderTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.cache = MemoryCache()
        self.cache_patch = patch.object(shiprocket.cache, "get_redis", return_value=self.cache)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)
        self.requests = []
        self.sleep = AsyncMock()

    def client(self, answer):
        def handle(request):
            self.requests.append(request)
            if request.url.path.endswith("/auth/login"):
                return httpx.Response(200, json={"token": f"token-{len(self.requests)}"})
            return answer(request)

        return shiprocket.ShiprocketClient(
            CREDS, transport=httpx.MockTransport(handle), sleep=self.sleep
        )

    async def test_auth_and_booking_use_documented_path_and_server_token(self):
        client = self.client(
            lambda r: httpx.Response(200, json={"order_id": 100, "shipment_id": 200})
        )
        result = await client.create_order(booking())
        self.assertEqual(result.provider_shipment_id, "200")
        self.assertEqual(self.requests[-1].url.path, "/v1/external/orders/create/adhoc")
        self.assertEqual(self.requests[-1].headers["authorization"], "Bearer token-1")
        login = json.loads(self.requests[0].content)
        self.assertEqual(login, {"email": CREDS.email, "password": CREDS.password})
        sent = json.loads(self.requests[-1].content)
        self.assertEqual(sent["billing_phone"], "9876543210")
        self.assertEqual(sent["sub_total"], 970)
        self.assertEqual(sent["payment_method"], "COD")
        self.assertEqual(sent["weight"], 0.75)
        self.assertNotIn("password", sent)

    async def test_expired_token_is_renewed_once_after_401(self):
        attempts = 0

        def answer(request):
            nonlocal attempts
            attempts += 1
            return httpx.Response(401 if attempts == 1 else 200, json={"data": {}})

        client = self.client(answer)
        await client.pickup_locations()
        self.assertEqual(attempts, 2)
        self.assertEqual(sum(r.url.path.endswith("/auth/login") for r in self.requests), 2)

    async def test_repeated_401_does_not_loop(self):
        client = self.client(lambda r: httpx.Response(401))
        with self.assertRaises(ShippingProviderError):
            await client.pickup_locations()
        self.assertEqual(len(self.requests), 4)

    async def test_long_lived_worker_refreshes_memory_token(self):
        client = self.client(lambda r: httpx.Response(200, json={"data": {}}))
        with patch.object(shiprocket.time, "monotonic", return_value=0):
            await client.pickup_locations()
        self.cache.data.clear()
        with patch.object(shiprocket.time, "monotonic", return_value=4000):
            await client.pickup_locations()
        self.assertEqual(sum(r.url.path.endswith("/auth/login") for r in self.requests), 2)

    async def test_bad_login_does_not_expose_credentials(self):
        client = shiprocket.ShiprocketClient(
            CREDS,
            transport=httpx.MockTransport(
                lambda r: httpx.Response(401, json={"message": "bad password"})
            ),
        )
        with self.assertRaises(ShippingProviderError) as error:
            await client.pickup_locations()
        self.assertNotIn(CREDS.password, str(error.exception))

    async def test_rate_limit_retries_reads_with_bounded_backoff(self):
        attempts = 0

        def answer(request):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return httpx.Response(429, headers={"Retry-After": "600"})
            return httpx.Response(200, json={"data": {}})

        await self.client(answer).pickup_locations()
        self.assertEqual(attempts, 3)
        self.assertEqual([c.args[0] for c in self.sleep.await_args_list], [8, 8])

    async def test_create_timeout_is_ambiguous_and_never_retried(self):
        def answer(request):
            raise httpx.ReadTimeout("timeout", request=request)

        client = self.client(answer)
        with self.assertRaises(ShippingProviderError) as error:
            await client.create_order(booking())
        self.assertTrue(error.exception.ambiguous)
        self.assertEqual(len(self.requests), 2)
        self.sleep.assert_not_awaited()

    async def test_read_timeout_retries_only_configured_number(self):
        def answer(request):
            raise httpx.ReadTimeout("timeout", request=request)

        with self.assertRaises(ShippingProviderError) as error:
            await self.client(answer).track("AWB123")
        self.assertFalse(error.exception.ambiguous)
        self.assertEqual(len(self.requests), 4)

    async def test_create_5xx_never_retries(self):
        with self.assertRaises(ShippingProviderError) as error:
            await self.client(lambda r: httpx.Response(503)).create_order(booking())
        self.assertTrue(error.exception.ambiguous)
        self.assertEqual(len(self.requests), 2)

    async def test_missing_create_identifiers_are_ambiguous(self):
        with self.assertRaises(ShippingProviderError) as error:
            await self.client(lambda r: httpx.Response(200, json={})).create_order(booking())
        self.assertTrue(error.exception.ambiguous)

    async def test_serviceability_preserves_official_rates(self):
        client = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "data": {
                        "recommended_courier_company_id": 10,
                        "available_courier_companies": [
                            {
                                "courier_company_id": 10,
                                "courier_name": "Courier",
                                "freight_charge": 44.50,
                                "cod_charges": 20,
                                "rate": 64.50,
                                "cod": 1,
                                "etd": "Nov 2, 2026",
                            }
                        ],
                    }
                },
            )
        )
        result = await client.check_rates(
            RateQuery("682001", "411001", PARCEL, True, Decimal("970"))
        )
        self.assertEqual(result[0].total_charge, Decimal("64.5"))
        self.assertTrue(result[0].is_recommended)
        self.assertEqual(self.requests[-1].url.params["cod"], "1")

    async def test_awb_assignment_parses_documented_response(self):
        client = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "awb_assign_status": 1,
                    "response": {
                        "data": {
                            "awb_code": "AWB123",
                            "courier_company_id": 10,
                            "courier_name": "Courier",
                            "applied_weight": 0.75,
                        }
                    },
                },
            )
        )
        result = await client.assign_awb("200", "10")
        self.assertEqual(result.awb_code, "AWB123")
        self.assertEqual(
            json.loads(self.requests[-1].content), {"shipment_id": 200, "courier_id": 10}
        )

    async def test_awb_explicit_refusal_is_safe_failure(self):
        with self.assertRaises(ShippingProviderError) as error:
            await self.client(
                lambda r: httpx.Response(
                    200,
                    json={
                        "awb_assign_status": 0,
                        "response": {"data": {"awb_assign_error": "Wallet balance"}},
                    },
                )
            ).assign_awb("200", None)
        self.assertFalse(error.exception.ambiguous)

    async def test_async_awb_acceptance_is_unconfirmed(self):
        with self.assertRaises(ShippingProviderError) as error:
            await self.client(
                lambda r: httpx.Response(200, json={"success": True, "message": "Processing"})
            ).assign_awb("200", None)
        self.assertTrue(error.exception.ambiguous)

    async def test_pickup_uses_arrays_and_provider_confirmation(self):
        client = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "pickup_status": 1,
                    "response": {
                        "pickup_scheduled_date": "2026-11-01",
                        "pickup_token_number": "PICK123",
                    },
                },
            )
        )
        result = await client.schedule_pickup("200", AT.date())
        self.assertEqual(result.token_number, "PICK123")
        self.assertEqual(
            json.loads(self.requests[-1].content),
            {"shipment_id": [200], "pickup_date": ["2026-10-29"]},
        )

    async def test_label_requires_success_flag_and_https(self):
        client = self.client(
            lambda r: httpx.Response(
                200, json={"label_created": 1, "label_url": "https://files.invalid/label.pdf"}
            )
        )
        self.assertEqual(await client.generate_label("200"), "https://files.invalid/label.pdf")
        bad = self.client(
            lambda r: httpx.Response(
                200, json={"label_created": 1, "label_url": "javascript:alert(1)"}
            )
        )
        with self.assertRaises(ShippingProviderError):
            await bad.generate_label("200")

    async def test_manifest_already_generated_prints_existing(self):
        def answer(request):
            if request.url.path.endswith("/generate"):
                return httpx.Response(400, json={"already_manifested_shipment_ids": [200]})
            return httpx.Response(200, json={"manifest_url": "https://files.invalid/manifest.pdf"})

        result = await self.client(answer).generate_manifest("200", "100")
        self.assertEqual(result, "https://files.invalid/manifest.pdf")
        self.assertEqual(json.loads(self.requests[-1].content), {"order_ids": [100]})

    async def test_cancel_requires_documented_204_confirmation(self):
        await self.client(lambda r: httpx.Response(204)).cancel_order("100")
        self.assertEqual(json.loads(self.requests[-1].content), {"ids": [100]})
        with self.assertRaises(ShippingProviderError) as error:
            await self.client(
                lambda r: httpx.Response(202, json={"message": "pending"})
            ).cancel_order("100")
        self.assertTrue(error.exception.ambiguous)

    async def test_lookup_requires_exact_channel_reference(self):
        client = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "data": [
                        {"id": 99, "channel_order_id": "12345-10", "shipments": {"id": 199}},
                        {"id": 100, "channel_order_id": "12345-1", "shipments": {"id": 200}},
                    ]
                },
            )
        )
        result = await client.find_order("12345-1")
        self.assertEqual(result.provider_order_id, "100")

    async def test_tracking_parses_official_scans_and_india_time(self):
        client = self.client(
            lambda r: httpx.Response(
                200,
                json={
                    "tracking_data": {
                        "shipment_status": 7,
                        "track_url": "https://courier.invalid/track",
                        "shipment_track": [
                            {"current_status": "Delivered", "courier_name": "Courier"}
                        ],
                        "shipment_track_activities": [
                            {
                                "date": "2026-10-29 15:30:00",
                                "sr-status": "7",
                                "sr-status-label": "Delivered",
                                "activity": "Handed to recipient",
                                "status": "DLVD",
                                "location": "Kochi",
                            }
                        ],
                    }
                },
            )
        )
        result = await client.track("AWB123")
        self.assertEqual(result.status_code, 7)
        self.assertEqual(result.scans[0].occurred_at.astimezone(timezone.utc), AT)


class StateTests(unittest.TestCase):
    def order_snapshot(self):
        return SimpleNamespace(
            created_at=AT,
            delivery_name="Test Buyer",
            delivery_address_line_1="Main Road",
            delivery_address_line_2=None,
            delivery_city="Kochi",
            delivery_state="Kerala",
            delivery_postal_code="682001",
            delivery_country="India",
            contact_email="buyer@example.com",
            delivery_phone="+919876543210",
            total_amount=Decimal("1070"),
            shipping_amount=Decimal("50"),
            cod_fee=Decimal("20"),
            discount_amount=Decimal("0"),
            items=[
                SimpleNamespace(
                    product_name="Kurta",
                    variant_name="M",
                    sku="KURTA-M",
                    quantity=1,
                    unit_price=Decimal("1000"),
                    gst_rate=Decimal("5"),
                    hsn_code="6204",
                )
            ],
        )

    def test_prepaid_booking_preserves_the_agreed_tax_and_shipping_total(self):
        order = self.order_snapshot()
        row = shipment(
            payment_mode="PREPAID",
            cod_amount=Decimal("0"),
            pickup_location="Store",
            weight_kg=PARCEL.weight_kg,
            length_cm=PARCEL.length_cm,
            breadth_cm=PARCEL.breadth_cm,
            height_cm=PARCEL.height_cm,
        )
        result = ShipmentService(None, row.tenant_id)._booking(row, order, None)
        payload = shiprocket.booking_payload(result)
        self.assertEqual(payload["payment_method"], "Prepaid")
        self.assertEqual(payload["sub_total"], 1070)
        self.assertEqual(payload["shipping_charges"], 50)
        self.assertEqual(payload["transaction_charges"], 20)

    def test_cod_advance_is_deducted_from_the_courier_collection_amount(self):
        order = self.order_snapshot()
        row = shipment(
            payment_mode="COD",
            cod_amount=Decimal("870"),
            pickup_location="Store",
            weight_kg=PARCEL.weight_kg,
            length_cm=PARCEL.length_cm,
            breadth_cm=PARCEL.breadth_cm,
            height_cm=PARCEL.height_cm,
        )
        result = ShipmentService(None, row.tenant_id)._booking(row, order, None)
        self.assertEqual(result.sub_total, Decimal("870"))
        self.assertEqual(result.total_discount, Decimal("200"))
        self.assertEqual(order.total_amount, Decimal("1070"))

    def test_delivery_and_returns_cannot_regress(self):
        for current in (
            ShipmentState.DELIVERED,
            ShipmentState.CANCELLED,
            ShipmentState.RETURNED_TO_ORIGIN,
        ):
            for target in ShipmentState:
                self.assertFalse(can_move(current, target))
        self.assertFalse(can_move(ShipmentState.IN_TRANSIT, ShipmentState.READY_TO_SHIP))
        self.assertFalse(can_move(ShipmentState.RETURN_TO_ORIGIN, ShipmentState.DELIVERED))
        self.assertTrue(can_move(ShipmentState.RETURN_TO_ORIGIN, ShipmentState.RETURNED_TO_ORIGIN))

    def test_order_paths_follow_stock_and_payment_lifecycle(self):
        for target in (OrderStatus.SHIPPED, OrderStatus.DELIVERED, OrderStatus.RETURNED):
            current = OrderStatus.CONFIRMED
            path = order_path(current, target)
            self.assertEqual(path[-1], target)
            for step in path:
                self.assertIn(step, ALLOWED_TRANSITIONS[current])
                current = step
        self.assertEqual(order_path(OrderStatus.CANCELLED, OrderStatus.SHIPPED), [])

    def test_stale_event_is_ignored(self):
        row = shipment(state="IN_TRANSIT", last_event_at=AT)
        service = ShipmentService(None, row.tenant_id)
        update = TrackingUpdate("AWB123", 7, "Delivered", AT - timedelta(days=1), None, None, None)
        self.assertFalse(
            service._transition(row, ShipmentState.DELIVERED, update.occurred_at, update)
        )
        self.assertEqual(row.state, "IN_TRANSIT")

    def test_booking_reference_is_unique_across_tenants_and_attempts(self):
        first = SimpleNamespace(id=uuid4(), order_number="ORD-100001")
        second = SimpleNamespace(id=uuid4(), order_number="ORD-100001")
        self.assertNotEqual(
            ShipmentService.channel_order_id(first, 1), ShipmentService.channel_order_id(second, 1)
        )
        self.assertNotEqual(
            ShipmentService.channel_order_id(first, 1), ShipmentService.channel_order_id(first, 2)
        )
        self.assertLess(len(ShipmentService.channel_order_id(first, 1)), 50)

    def test_parcel_defaults_are_explicit_and_validated(self):
        with self.assertRaises(ValueError):
            PackageInput(weight_kg="0", length_cm="25", breadth_cm="20", height_cm="4")
        with self.assertRaises(ValueError):
            ProviderSettingsUpdate(is_enabled=True)
        self.assertIsNone(ShipmentService.package_defaults(None))

    def test_cod_balance_subtracts_actual_paid_amounts_only(self):
        order = SimpleNamespace(
            payment_method="CASH_ON_DELIVERY",
            total_amount=Decimal("1070"),
            payments=[
                SimpleNamespace(status="PAID", amount=Decimal("200")),
                SimpleNamespace(status="FAILED", amount=Decimal("100")),
            ],
        )
        self.assertEqual(ShipmentService.cod_amount(order), Decimal("870.00"))
        order.payment_method = "UPI"
        self.assertEqual(ShipmentService.cod_amount(order), Decimal("0"))

    def test_webhook_uses_documented_shipment_status_not_other_status_codes(self):
        update = shiprocket.parse_webhook(
            {
                "awb": "AWB123",
                "current_status_id": 7,
                "shipment_status_id": 18,
                "current_timestamp": "29 10 2026 15:30:00",
            }
        )
        self.assertEqual(update.status_code, 18)
        self.assertEqual(update.occurred_at.astimezone(timezone.utc), AT)

    def test_credentials_are_bound_to_the_intended_tenant(self):
        first, second = uuid4(), uuid4()
        settings = SimpleNamespace(
            shiprocket_email="first@example.com",
            shiprocket_password="first-secret",
            shiprocket_tenant_id=str(first),
            shiprocket_tenant_credentials={},
            shiprocket_api_url=CREDS.api_url,
            shiprocket_timeout_seconds=1,
            shiprocket_token_ttl_seconds=3600,
            shiprocket_read_retries=2,
        )
        with patch.object(shiprocket, "get_settings", return_value=settings):
            self.assertTrue(shiprocket.is_configured(first))
            self.assertFalse(shiprocket.is_configured(second))
            with self.assertRaises(ProviderNotConfiguredError):
                shiprocket.credentials(second)
            settings.shiprocket_tenant_credentials[second] = {
                "email": "second@example.com",
                "password": "second-secret",
            }
            self.assertEqual(shiprocket.credentials(second).email, "second@example.com")


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.row = shipment(pending_operation="CREATE", operation_status="UNKNOWN")
        self.session = SimpleNamespace(
            commit=AsyncMock(), rollback=AsyncMock(), add=lambda value: None
        )
        self.provider = SimpleNamespace(
            find_order=AsyncMock(return_value=None),
            create_order=AsyncMock(),
            get_order=AsyncMock(return_value=None),
            assign_awb=AsyncMock(),
            schedule_pickup=AsyncMock(),
        )
        self.service = ShipmentService(self.session, self.row.tenant_id, self.provider)

    async def test_unknown_booking_not_found_never_resends_create(self):
        with self.assertRaises(ServiceUnavailableError):
            await self.service._retry_create(self.row, uncertain=True)
        self.provider.create_order.assert_not_awaited()
        self.assertEqual(self.row.operation_status, "UNKNOWN")

    async def test_stale_in_progress_request_requires_reconciliation(self):
        self.row.pending_operation = "ASSIGN_AWB"
        self.row.operation_status = "IN_PROGRESS"
        self.row.state = "SHIPMENT_CREATED"
        self.service._lock = AsyncMock(return_value=self.row)
        with self.assertRaises(ConflictError):
            await self.service.assign_awb(self.row.order_id, self.row.id, "10")
        self.provider.assign_awb.assert_not_awaited()

    async def test_interrupted_operation_can_be_recovered_from_admin_actions(self):
        from app.shipments.serializers import actions

        self.row.operation_status = "IN_PROGRESS"
        self.assertIn("retry", actions(self.row))

    async def test_definitive_awb_failure_allows_choosing_another_courier(self):
        from app.shipments.serializers import actions

        self.row.state = "SHIPMENT_CREATED"
        self.row.pending_operation = "ASSIGN_AWB"
        self.row.operation_status = "FAILED"
        self.assertIn("assign_awb", actions(self.row))

    async def test_disabled_store_cannot_retry_a_definitively_failed_booking(self):
        self.service._order = AsyncMock(return_value=None)
        self.service.create_blocked_reason = lambda order: None
        self.service._require_enabled = AsyncMock(side_effect=ConflictError("Booking disabled"))
        self.service._book = AsyncMock()
        with self.assertRaises(ConflictError):
            await self.service._retry_create(self.row, uncertain=False)
        self.service._book.assert_not_awaited()

    async def test_collected_parcel_cannot_return_to_pickup_scheduled(self):
        self.row.state = "DELIVERY_EXCEPTION"
        self.row.picked_up_at = AT
        update = TrackingUpdate("AWB123", 3, "Pickup scheduled", AT, None, None, None)
        self.assertFalse(
            self.service._transition(self.row, ShipmentState.PICKUP_SCHEDULED, AT, update)
        )

    async def test_unknown_booking_found_adopts_existing_order(self):
        found = BookedOrder("100", "200", "AWB123")
        self.provider.find_order.return_value = found
        self.service._adopt = AsyncMock()
        await self.service._retry_create(self.row, uncertain=True)
        self.service._adopt.assert_awaited_once_with(self.row, found)
        self.provider.create_order.assert_not_awaited()

    async def test_unknown_booking_lookup_error_preserves_unknown_outcome(self):
        self.provider.find_order.side_effect = ShippingProviderError("Unavailable", retryable=True)
        with self.assertRaises(ServiceUnavailableError):
            await self.service._retry_create(self.row, uncertain=True)
        self.assertEqual(self.row.operation_status, "UNKNOWN")
        self.provider.create_order.assert_not_awaited()

    async def test_unknown_awb_is_reconciled_without_resending(self):
        self.row.pending_operation = ShipmentOperation.ASSIGN_AWB.value
        self.service._lock = AsyncMock(return_value=self.row)
        with self.assertRaises(ServiceUnavailableError):
            await self.service.retry(self.row.order_id, self.row.id)
        self.provider.assign_awb.assert_not_awaited()

    async def test_unknown_pickup_is_not_resent(self):
        self.row.pending_operation = ShipmentOperation.SCHEDULE_PICKUP.value
        self.provider.track = AsyncMock(
            return_value=TrackingUpdate("AWB123", 1, "AWB Assigned", AT, None, None, None)
        )
        self.service._lock = AsyncMock(return_value=self.row)
        self.service.apply_update = AsyncMock()
        with self.assertRaises(ServiceUnavailableError):
            await self.service.retry(self.row.order_id, self.row.id)
        self.provider.schedule_pickup.assert_not_awaited()

    async def test_unconfirmed_booking_cannot_be_released_for_rebooking(self):
        self.row.provider_order_id = None
        with self.assertRaises(ServiceUnavailableError):
            await self.service._call_cancel(self.row)
        self.assertNotEqual(self.row.state, "CANCELLED")

    async def test_booking_does_not_mark_order_shipped(self):
        self.row.state = ShipmentState.PENDING_FULFILMENT.value
        self.service._lock = AsyncMock(return_value=self.row)
        self.service._sync_order = AsyncMock()
        await self.service._adopt(self.row, BookedOrder("100", "200"))
        self.assertEqual(self.row.state, "SHIPMENT_CREATED")
        self.service._sync_order.assert_not_awaited()

    async def test_webhook_rejects_missing_and_invalid_secret_before_db_access(self):
        settings = SimpleNamespace(shiprocket_webhook_token="test-webhook-key")
        request = SimpleNamespace(body=AsyncMock(return_value=b"{}"))
        with patch.object(router, "get_settings", return_value=settings):
            for token in (None, "", "wrong"):
                with self.assertRaises(AuthenticationError):
                    await router.tracking_webhook(request, token, None)
        request.body.assert_not_awaited()

    async def test_authenticated_webhook_dispatches_only_valid_json(self):
        settings = SimpleNamespace(shiprocket_webhook_token="test-webhook-key")

        async def chunks():
            yield b'{"awb":"AWB123"}'

        request = SimpleNamespace(stream=chunks)
        with (
            patch.object(router, "get_settings", return_value=settings),
            patch.object(
                router, "handle_webhook", new=AsyncMock(return_value="applied")
            ) as handler,
        ):
            await router.tracking_webhook(request, "test-webhook-key", self.session)
        handler.assert_awaited_once_with(self.session, {"awb": "AWB123"})

    async def test_duplicate_events_preserved_once_and_order_sync_can_recover(self):
        self.session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
        self.session.add = lambda value: added.append(value)
        self.service.orders.get = AsyncMock(return_value=None)
        self.service._sync_order = AsyncMock()
        added = []
        update = TrackingUpdate("AWB123", 18, "In transit", AT, None, None, None)
        await self.service.apply_update(self.row, update, shiprocket_source())
        key = added[0].dedupe_key
        self.session.scalars.return_value = SimpleNamespace(all=lambda: [key])
        added.clear()
        await self.service.apply_update(self.row, update, shiprocket_source())
        self.assertEqual(added, [])
        self.assertEqual(self.service._sync_order.await_count, 2)

    async def test_paid_rto_preserves_refund_rules_and_keeps_diagnostics_private(self):
        self.row.state = "RETURNED_TO_ORIGIN"
        self.row.picked_up_at = AT
        self.service._lock = AsyncMock(return_value=self.row)
        order = SimpleNamespace(id=self.row.order_id, order_number="ORD-1", status="SHIPPED")
        orders = SimpleNamespace(
            get=AsyncMock(return_value=order),
            update_status=AsyncMock(side_effect=ConflictError("Refund workflow required")),
        )
        events = []
        self.session.add = events.append
        with patch("app.shipments.service.OrderService", return_value=orders):
            await self.service._sync_order(self.row)
            await self.service._sync_order(self.row)
        self.assertEqual(self.row.state, "RETURNED_TO_ORIGIN")
        self.assertEqual(len(events), 0)
        self.assertIn("Refund workflow required", self.row.last_error)

    async def test_cancellation_webhook_clears_legacy_tracking_and_pending_request(self):
        self.row.pending_operation = "CANCEL"
        self.row.operation_status = "UNKNOWN"
        self.row.last_error = "Tracking: temporarily unavailable"
        self.session.scalars = AsyncMock(return_value=SimpleNamespace(all=lambda: []))
        order = SimpleNamespace(tracking_number="AWB123", tracking_url=None, courier_name="Courier")
        self.service.orders.get = AsyncMock(return_value=order)
        self.service._sync_order = AsyncMock()
        update = TrackingUpdate("AWB123", 8, "Cancelled", AT, None, None, None)
        await self.service.apply_update(self.row, update, shiprocket_source())
        self.assertEqual(self.row.state, "CANCELLED")
        self.assertIsNone(self.row.pending_operation)
        self.assertIsNone(self.row.last_error)
        self.assertIsNone(order.tracking_number)
        self.assertIsNone(order.courier_name)


def shiprocket_source():
    from app.shipments.constants import ShipmentEventSource

    return ShipmentEventSource.WEBHOOK


if __name__ == "__main__":
    unittest.main()
