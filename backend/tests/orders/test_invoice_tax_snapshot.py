"""Invoices retain seller details frozen at order placement."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from app.orders.constants import GstType, OrderStatus
from app.orders.serializers import invoice_read


def test_invoice_uses_order_seller_snapshot_after_settings_change():
    order = SimpleNamespace(
        items=[], created_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
        status=OrderStatus.DELIVERED.value, order_number="ZN-1001",
        gst_type=GstType.INTRA_STATE.value, place_of_supply="Karnataka (29)",
        seller_gstin="29ABCDE1234F1Z5", seller_legal_name="Original Legal Name",
        seller_address="Original Registered Address", seller_state="Karnataka",
        seller_state_code="29", invoice_prefix="OLD-", shipping_sac_code="9967",
        gst_registration_status="REGISTERED", charges_gst_rate=Decimal("18.00"),
        delivery_name="Buyer", delivery_address_line_1="Street 1",
        delivery_address_line_2=None, delivery_city="Bengaluru",
        delivery_state="Karnataka", delivery_postal_code="560001",
        delivery_country="India", contact_email=None, delivery_phone="9000000000",
        subtotal=Decimal("0.00"), discount_amount=Decimal("0.00"),
        shipping_amount=Decimal("0.00"), cod_fee=Decimal("0.00"),
        tax_amount=Decimal("0.00"), tax_included_amount=Decimal("0.00"),
        total_amount=Decimal("0.00"), cgst_amount=Decimal("0.00"),
        sgst_amount=Decimal("0.00"), igst_amount=Decimal("0.00"),
    )
    changed_settings = SimpleNamespace(
        legal_name="Changed Name", address="Changed Address", state="Maharashtra",
        state_code="27", gstin="27ABCDE1234F1Z5", invoice_prefix="NEW-",
        shipping_sac_code="9983",
    )

    invoice = invoice_read(order, changed_settings, "INR")

    assert invoice.invoice_number == "OLD-ZN-1001"
    assert invoice.seller.name == "Original Legal Name"
    assert invoice.seller.address == "Original Registered Address"
    assert invoice.seller.gstin == "29ABCDE1234F1Z5"
    assert invoice.seller.state == "Karnataka"
