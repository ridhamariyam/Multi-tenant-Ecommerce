"""The PDFs an order produces: GST invoice, packing slip and shipping label.

This module only lays out data. Every invoice figure comes from `InvoiceRead`,
the same model the JSON invoice endpoint returns (built by
`orders.serializers.invoice_read` from what the order froze at checkout), so
the PDF can never disagree with the JSON invoice or the order.

The packing slip and label show no prices or tax -- they go to the packing
table and on the parcel. A courier's own label (AWB barcode) needs a courier
integration; this label is the store's address label for the box.
"""

from __future__ import annotations

import io
import re
from decimal import Decimal
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, A6
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.orders.constants import GstType, OrderStatus
from app.orders.models import Order
from app.orders.schemas import InvoiceRead
from app.pricing.models import GstSettings

PDF_MEDIA_TYPE = "application/pdf"

_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")

_styles = getSampleStyleSheet()
_BODY = ParagraphStyle("body", parent=_styles["Normal"], fontSize=8, leading=10)
_SMALL = ParagraphStyle("small", parent=_BODY, fontSize=7, leading=9)
_BOLD = ParagraphStyle("bold", parent=_BODY, fontName="Helvetica-Bold")
_RIGHT = ParagraphStyle("right", parent=_BODY, alignment=TA_RIGHT)
# The line-item table is wide, so its cells use a smaller face.
_CELL = ParagraphStyle("cell", parent=_BODY, fontSize=7, leading=8.5)
_CELL_BOLD = ParagraphStyle("cell_bold", parent=_CELL, fontName="Helvetica-Bold")
_CELL_RIGHT = ParagraphStyle("cell_right", parent=_CELL, alignment=TA_RIGHT)
_TITLE = ParagraphStyle(
    "title", parent=_styles["Title"], fontSize=15, leading=18, spaceAfter=2 * mm
)

_GRID = colors.HexColor("#B8BCC4")
_SHADE = colors.HexColor("#EEF0F4")

# Side-by-side address boxes.
_BOXES_STYLE = [
    ("BOX", (0, 0), (-1, -1), 0.5, _GRID),
    ("INNERGRID", (0, 0), (-1, -1), 0.5, _GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]
# A list of lines under a shaded header row.
_LINES_STYLE = [
    ("BACKGROUND", (0, 0), (-1, 0), _SHADE),
    ("BOX", (0, 0), (-1, -1), 0.5, _GRID),
    ("INNERGRID", (0, 0), (-1, -1), 0.25, _GRID),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
]


def invoice_filename(invoice: InvoiceRead) -> str:
    """`INV-ORD-100001.pdf`; anything unsafe in a header (e.g. '/') becomes '-'."""
    stem = _SAFE_FILENAME.sub("-", invoice.invoice_number).strip("-.") or "invoice"
    return f"{stem}.pdf"


def _amount(value: Decimal | None) -> str:
    return f"{(value or Decimal('0')):,.2f}"


def _para(text: str | None, style: ParagraphStyle = _BODY) -> Paragraph:
    return Paragraph(escape(text or "-"), style)


def _lines_of(*parts: str | None) -> str:
    return "<br/>".join(escape(part) for part in parts if part)


def _document(
    buffer: io.BytesIO, title: str, store_name: str, *, pagesize=A4, margin: float = 14 * mm
) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer,
        pagesize=pagesize,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
        title=title,
        author=store_name,
    )


def render_invoice_pdf(
    invoice: InvoiceRead,
    *,
    store_name: str,
    customer_phone: str | None = None,
    customer_email: str | None = None,
) -> bytes:
    """Build the invoice PDF and return its bytes."""
    buffer = io.BytesIO()
    doc = _document(buffer, f"Tax Invoice {invoice.invoice_number}", store_name)
    width = doc.width
    story = [Paragraph("TAX INVOICE", _TITLE)]

    if invoice.order_status in {OrderStatus.CANCELLED, OrderStatus.RETURNED}:
        story.append(
            Paragraph(
                f"<b>Order status: {escape(invoice.order_status.value)}</b>",
                ParagraphStyle("warn", parent=_BODY, textColor=colors.HexColor("#B42318")),
            )
        )
        story.append(Spacer(1, 2 * mm))

    story.append(_header(invoice, store_name, width))
    story.append(Spacer(1, 4 * mm))
    story.append(_parties(invoice, customer_phone, customer_email, width))
    story.append(Spacer(1, 4 * mm))
    story.append(_items(invoice, width))
    story.append(Spacer(1, 3 * mm))
    story.append(_totals(invoice, width))
    story.append(Spacer(1, 6 * mm))
    story.append(
        _para(
            f"All amounts in {invoice.currency}. This is a computer-generated invoice "
            "and does not need a signature.",
            _SMALL,
        )
    )

    doc.build(story)
    return buffer.getvalue()


def _header(invoice: InvoiceRead, store_name: str, width: float) -> Table:
    seller = invoice.seller
    seller_block = Paragraph(
        f"<b>{escape(store_name)}</b><br/>"
        + _lines_of(
            seller.name if seller.name and seller.name != store_name else None,
            seller.address,
            f"State: {seller.state} ({seller.state_code})" if seller.state else None,
            f"GSTIN: {seller.gstin}" if seller.gstin else None,
        ),
        _BODY,
    )
    supply = {
        GstType.INTRA_STATE: "Intra-state (CGST + SGST)",
        GstType.INTER_STATE: "Inter-state (IGST)",
    }.get(invoice.gst_type, "Tax classification unavailable")
    meta = [
        ("Invoice number", invoice.invoice_number),
        ("Invoice date", invoice.invoice_date.strftime("%d %b %Y")),
        ("Order number", invoice.order_number),
        ("Place of supply", invoice.place_of_supply or "-"),
        ("Supply type", supply),
    ]
    meta_table = Table(
        [[_para(label, _BOLD), _para(value)] for label, value in meta],
        colWidths=[28 * mm, width / 2 - 30 * mm],
    )
    meta_table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)])
    )
    table = Table([[seller_block, meta_table]], colWidths=[width / 2, width / 2])
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return table


def _parties(
    invoice: InvoiceRead, phone: str | None, email: str | None, width: float
) -> Table:
    buyer = invoice.buyer
    address = _lines_of(
        buyer.name,
        buyer.address,
        f"State: {buyer.state}" + (f" ({buyer.state_code})" if buyer.state_code else "")
        if buyer.state
        else None,
    )
    contact = _lines_of(
        f"Phone: {phone}" if phone else None,
        f"Email: {email}" if email else None,
    )
    # The order stores one address, used for both billing and delivery.
    billing = address + ("<br/>" + contact if contact else "")
    bill_to = Paragraph("<b>Bill to</b><br/>" + billing, _BODY)
    ship_to = Paragraph("<b>Ship to</b><br/>" + address, _BODY)
    table = Table([[bill_to, ship_to]], colWidths=[width / 2, width / 2])
    table.setStyle(TableStyle(_BOXES_STYLE))
    return table


def _items(invoice: InvoiceRead, width: float) -> Table:
    intra = invoice.gst_type is GstType.INTRA_STATE
    tax_heads = (
        ["CGST", "SGST"]
        if intra
        else ["IGST"]
        if invoice.tax_split_known
        else ["Tax split unavailable"]
    )
    header = ["#", "Item", "HSN/SAC", "Qty", "Rate", "Disc.", "Taxable", "GST%"]
    header += tax_heads + ["Amount"]

    rows: list[list] = [[_para(h, _CELL_BOLD) for h in header]]
    for index, line in enumerate(invoice.lines, start=1):
        item = escape(line.description) + (
            f"<br/><font size=6>SKU: {escape(line.sku)}</font>" if line.sku else ""
        )
        taxes = (
            [line.cgst_amount, line.sgst_amount]
            if intra
            else [line.igst_amount]
            if invoice.tax_split_known
            else [None]
        )
        rows.append(
            [
                _para(str(index), _CELL),
                Paragraph(item, _CELL),
                _para(line.hsn_code, _CELL),
                _para(str(line.quantity), _CELL_RIGHT),
                _para(_amount(line.unit_price), _CELL_RIGHT),
                _para(_amount(line.discount), _CELL_RIGHT),
                _para(_amount(line.taxable_value), _CELL_RIGHT),
                _para(f"{line.gst_rate:.2f}", _CELL_RIGHT),
                *[
                    _para(_amount(tax), _CELL_RIGHT)
                    if tax is not None
                    else _para("—", _CELL_RIGHT)
                    for tax in taxes
                ],
                _para(_amount(line.total), _CELL_RIGHT),
            ]
        )

    fixed = [6 * mm, 0, 15 * mm, 8 * mm, 16 * mm, 14 * mm, 17 * mm, 10 * mm]
    fixed += [14 * mm] * len(tax_heads) + [17 * mm]
    fixed[1] = width - sum(fixed)
    table = Table(rows, colWidths=fixed, repeatRows=1)
    table.setStyle(
        TableStyle(
            _LINES_STYLE
            + [("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2)]
        )
    )
    return table


def _totals(invoice: InvoiceRead, width: float) -> Table:
    totals = invoice.totals
    rows = [
        ("Subtotal", totals.subtotal),
        ("Discount", -totals.discount if totals.discount else totals.discount),
        ("Shipping charges", totals.shipping),
        ("COD charges", totals.cod_fee),
        ("Taxable value", totals.taxable_value),
    ]
    if not invoice.tax_split_known:
        rows.append(("Tax (classification unavailable)", totals.tax_amount))
    elif invoice.gst_type is GstType.INTRA_STATE:
        rows += [("CGST", totals.cgst_amount), ("SGST", totals.sgst_amount)]
    else:
        rows += [("IGST", totals.igst_amount)]
    if invoice.tax_split_known:
        rows.append(("Total tax", totals.tax_amount))

    data = [[_para(label), _para(_amount(value), _RIGHT)] for label, value in rows]
    data.append(
        [
            _para(f"Grand total ({invoice.currency})", _BOLD),
            Paragraph(f"<b>{_amount(totals.total)}</b>", _RIGHT),
        ]
    )
    table = Table(data, colWidths=[40 * mm, 30 * mm], hAlign="RIGHT")
    table.setStyle(
        TableStyle(
            [
                ("LINEABOVE", (0, -1), (-1, -1), 0.75, colors.black),
                ("BACKGROUND", (0, -1), (-1, -1), _SHADE),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5),
            ]
        )
    )
    return table


def _address(order: Order) -> str:
    return _lines_of(
        order.delivery_name,
        order.delivery_address_line_1,
        order.delivery_address_line_2,
        f"{order.delivery_city}, {order.delivery_state} {order.delivery_postal_code}",
        order.delivery_country,
        f"Phone: {order.delivery_phone}",
    )


def _sender(store_name: str, seller: GstSettings | None) -> str:
    if seller is None:
        return _lines_of(store_name)
    legal_name = seller.legal_name if seller.legal_name != store_name else None
    return _lines_of(store_name, legal_name, seller.address)


def render_packing_slip(order: Order, *, store_name: str, seller: GstSettings | None) -> bytes:
    buffer = io.BytesIO()
    doc = _document(buffer, f"Packing slip {order.order_number}", store_name)
    width = doc.width
    story = [Paragraph("PACKING SLIP", _TITLE)]

    meta = Table(
        [
            [
                Paragraph("<b>From</b><br/>" + _sender(store_name, seller), _BODY),
                Paragraph("<b>Ship to</b><br/>" + _address(order), _BODY),
            ],
        ],
        colWidths=[width / 2, width / 2],
    )
    meta.setStyle(TableStyle(_BOXES_STYLE))
    story += [
        Paragraph(
            f"<b>Order</b> {escape(order.order_number)} &nbsp;&nbsp; "
            f"<b>Date</b> {order.created_at:%d %b %Y} &nbsp;&nbsp; "
            f"<b>Payment</b> {escape(order.payment_method)}"
            + (
                f" &nbsp;&nbsp; <b>Courier</b> {escape(order.courier_name)}"
                if order.courier_name
                else ""
            )
            + (
                f" &nbsp;&nbsp; <b>Tracking</b> {escape(order.tracking_number)}"
                if order.tracking_number
                else ""
            ),
            _BODY,
        ),
        Spacer(1, 3 * mm),
        meta,
        Spacer(1, 4 * mm),
    ]

    rows = [[Paragraph(h, _CELL_BOLD) for h in ("#", "Item", "SKU", "Qty", "Packed")]]
    for index, item in enumerate(order.items, start=1):
        rows.append(
            [
                Paragraph(str(index), _CELL),
                Paragraph(escape(f"{item.product_name} - {item.variant_name}"), _CELL),
                Paragraph(escape(item.sku), _CELL),
                Paragraph(str(item.quantity), _CELL_RIGHT),
                Paragraph("&#9744;", _CELL),
            ]
        )
    units = sum(item.quantity for item in order.items)
    rows.append(
        [
            "",
            Paragraph("<b>Total units</b>", _CELL),
            "",
            Paragraph(f"<b>{units}</b>", _CELL_RIGHT),
            "",
        ]
    )
    widths = [8 * mm, width - 78 * mm, 40 * mm, 15 * mm, 15 * mm]
    table = Table(rows, colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle(_LINES_STYLE))
    story.append(table)
    doc.build(story)
    return buffer.getvalue()


def _label_box(order: Order, width: float, *, store_name: str, seller: GstSettings | None):
    """One parcel label: ship-to, order number, COD amount, courier, sender."""
    cod_due = sum(
        (p.amount for p in order.payments if p.provider == "COD" and p.status == "PENDING"), 0
    )
    lines = [
        Paragraph(f"<b>SHIP TO</b><br/>{_address(order)}", _BODY),
        Spacer(1, 3 * mm),
        Paragraph(f"<b>Order:</b> {escape(order.order_number)}", _BOLD),
        Paragraph(
            f"<b>{'COD - collect' if cod_due else 'PREPAID'}</b>"
            + (f" {cod_due:,.2f}" if cod_due else ""),
            _BOLD,
        ),
    ]
    if order.courier_name or order.tracking_number:
        lines.append(
            Paragraph(
                escape(" ".join(p for p in (order.courier_name, order.tracking_number) if p)),
                _BODY,
            )
        )
    lines += [Spacer(1, 3 * mm), Paragraph(f"<b>FROM</b><br/>{_sender(store_name, seller)}", _BODY)]
    box = Table([[lines]], colWidths=[width])
    box.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 1, colors.black)]))
    return box


def render_shipping_label(order: Order, *, store_name: str, seller: GstSettings | None) -> bytes:
    """An A6 address label for the parcel (order number, COD amount, addresses)."""
    buffer = io.BytesIO()
    doc = _document(
        buffer, f"Shipping label {order.order_number}", store_name, pagesize=A6, margin=6 * mm
    )
    doc.build([_label_box(order, doc.width, store_name=store_name, seller=seller)])
    return buffer.getvalue()


def render_shipping_labels(
    orders: list[Order], *, store_name: str, seller: GstSettings | None
) -> bytes:
    """Many orders' labels in one PDF, one A6 label per page, in the given order."""
    buffer = io.BytesIO()
    doc = _document(
        buffer, f"Shipping labels ({len(orders)})", store_name, pagesize=A6, margin=6 * mm
    )
    story = []
    for index, order in enumerate(orders):
        if index:
            story.append(PageBreak())
        story.append(_label_box(order, doc.width, store_name=store_name, seller=seller))
    doc.build(story)
    return buffer.getvalue()
