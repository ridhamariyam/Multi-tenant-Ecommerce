"""Legacy invoice tax representation without database fixtures."""

from __future__ import annotations

import io
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from pypdf import PdfReader

from app.orders.constants import GstType
from app.orders.pdf import render_invoice_pdf
from app.orders.serializers import invoice_read


def _order(*, gst_type: str | None, tax: str, item_tax: str | None):
    tax_amount = Decimal(tax)
    item_tax_amount = Decimal(item_tax) if item_tax is not None else None
    item = SimpleNamespace(
        product_name="Cotton Kurta",
        variant_name="Blue / M",
        sku="KURTA-1",
        hsn_code="620442",
        quantity=1,
        unit_price=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        subtotal=Decimal("100.00"),
        taxable_amount=Decimal("100.00"),
        gst_rate=Decimal("18.00"),
        cgst_amount=None,
        sgst_amount=None,
        igst_amount=None,
        tax_amount=item_tax_amount,
    )
    return SimpleNamespace(
        items=[item],
        gst_type=gst_type,
        tax_amount=tax_amount,
        shipping_amount=Decimal("20.00"),
        cod_fee=Decimal("0.00"),
        delivery_state="Karnataka",
        delivery_address_line_1="1 MG Road",
        delivery_address_line_2=None,
        delivery_city="Bengaluru",
        delivery_postal_code="560001",
        delivery_country="India",
        seller_gstin=None,
        # Columns added with dynamic tax configuration: a legacy order has
        # no snapshot of them, so they read back as their migration defaults.
        seller_legal_name=None,
        seller_address=None,
        seller_state=None,
        seller_state_code=None,
        shipping_sac_code=None,
        charges_gst_rate=None,
        gst_registration_status=None,
        tax_included_amount=Decimal("0.00"),
        invoice_prefix="INV-",
        subtotal=Decimal("100.00"),
        discount_amount=Decimal("0.00"),
        place_of_supply="Karnataka",
        delivery_name="Test Buyer",
        delivery_phone="9876543210",
        created_at=datetime(2025, 1, 2, tzinfo=timezone.utc),
        status="PENDING",
        order_number="ORD-100001",
        cgst_amount=(
            tax_amount / 2
            if gst_type == GstType.INTRA_STATE.value
            else Decimal("0.00")
        ),
        sgst_amount=(
            tax_amount / 2
            if gst_type == GstType.INTRA_STATE.value
            else Decimal("0.00")
        ),
        igst_amount=(
            tax_amount
            if gst_type == GstType.INTER_STATE.value
            else Decimal("0.00")
        ),
        total_amount=Decimal("120.00") + tax_amount,
    )


def _pdf_text(invoice) -> str:
    content = render_invoice_pdf(invoice, store_name="ZEEN")
    return " ".join(PdfReader(io.BytesIO(content)).pages[0].extract_text().split())


def test_known_intra_state_invoice_keeps_cgst_sgst_split():
    order = _order(gst_type=GstType.INTRA_STATE.value, tax="18.00", item_tax="18.00")

    invoice = invoice_read(order, seller=None, currency="INR")

    assert invoice.tax_split_known is True
    assert invoice.gst_type is GstType.INTRA_STATE
    assert invoice.lines[0].cgst_amount == Decimal("9.00")
    assert invoice.lines[0].sgst_amount == Decimal("9.00")
    assert invoice.lines[0].igst_amount == Decimal("0")
    text = _pdf_text(invoice)
    assert "CGST" in text
    assert "SGST" in text


def test_known_inter_state_invoice_keeps_igst_split():
    order = _order(gst_type=GstType.INTER_STATE.value, tax="18.00", item_tax="18.00")

    invoice = invoice_read(order, seller=None, currency="INR")

    assert invoice.tax_split_known is True
    assert invoice.gst_type is GstType.INTER_STATE
    assert invoice.lines[0].cgst_amount == Decimal("0")
    assert invoice.lines[0].sgst_amount == Decimal("0")
    assert invoice.lines[0].igst_amount == Decimal("18.00")
    text = _pdf_text(invoice)
    assert "IGST" in text
    assert "Inter-state" in text


def test_unknown_legacy_tax_is_not_assigned_to_gst_head_or_shipping():
    order = _order(gst_type=None, tax="18.00", item_tax=None)
    # Simulates the historical migration's unsupported assignment before the
    # corrective migration has been applied. Serialization must still be safe.
    order.igst_amount = Decimal("18.00")
    current_seller_settings = SimpleNamespace(
        legal_name="Current Tenant Name",
        gstin="29ABCDE1234F1Z5",
        state="Karnataka",
        state_code="29",
        address="Current address",
        invoice_prefix="INV-",
        shipping_sac_code="9965",
    )

    invoice = invoice_read(order, seller=current_seller_settings, currency="INR")

    assert invoice.tax_split_known is False
    assert invoice.gst_type is None
    assert invoice.totals.tax_amount == Decimal("18.00")
    assert invoice.totals.cgst_amount == Decimal("0")
    assert invoice.totals.sgst_amount == Decimal("0")
    assert invoice.totals.igst_amount == Decimal("0")
    assert invoice.seller.gstin is None
    assert invoice.seller.state is None
    assert invoice.seller.state_code is None
    assert all(
        line.cgst_amount == line.sgst_amount == line.igst_amount == 0
        for line in invoice.lines
    )
    shipping = next(line for line in invoice.lines if line.description == "Shipping charges")
    assert shipping.total == Decimal("20.00")
    assert shipping.cgst_amount == shipping.sgst_amount == shipping.igst_amount == 0

    text = _pdf_text(invoice)
    assert "Tax classification unavailable" in text
    assert "Tax (classification unavailable)" in text
    assert "18.00" in text
    assert "CGST" not in text
    assert "SGST" not in text
    assert "IGST" not in text
    assert "Shipping charges" in text
