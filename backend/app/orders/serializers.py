"""Turn order rows into API payloads."""

from __future__ import annotations

from app.core.money import ZERO, money
from app.orders.constants import OrderStatus
from app.orders.models import Order
from app.orders.schemas import (
    DeliveryAddressRead,
    GstBreakdown,
    InvoiceLine,
    InvoiceParty,
    InvoiceRead,
    InvoiceTotals,
    OrderItemRead,
    OrderRead,
    OrderSummaryRead,
    OrderTrackingRead,
    ShipmentRead,
    TrackingEventRead,
)
from app.payments.serializers import payment_read
from app.pricing.gst import split_tax, state_code_for
from app.pricing.models import GstSettings
from app.shipments.schemas import CustomerShipmentRead


def delivery_address(order: Order) -> DeliveryAddressRead:
    return DeliveryAddressRead(
        full_name=order.delivery_name,
        phone=order.delivery_phone,
        address_line_1=order.delivery_address_line_1,
        address_line_2=order.delivery_address_line_2,
        city=order.delivery_city,
        state=order.delivery_state,
        postal_code=order.delivery_postal_code,
        country=order.delivery_country,
    )


def shipment_read(order: Order) -> ShipmentRead:
    return ShipmentRead(
        courier_name=order.courier_name,
        tracking_number=order.tracking_number,
        tracking_url=order.tracking_url,
    )


def gst_breakdown(order: Order) -> GstBreakdown | None:
    if order.gst_type is None:
        return None
    return GstBreakdown(
        gst_type=order.gst_type,
        place_of_supply=order.place_of_supply,
        cgst_amount=order.cgst_amount,
        sgst_amount=order.sgst_amount,
        igst_amount=order.igst_amount,
    )


def order_read(order: Order, currency: str) -> OrderRead:
    """`currency` comes from the tenant -- see `payments.serializers`."""
    return OrderRead(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        items=[OrderItemRead.model_validate(item) for item in order.items],
        subtotal=order.subtotal,
        coupon_code=order.coupon_code,
        discount_amount=order.discount_amount,
        shipping_amount=order.shipping_amount,
        cod_fee=order.cod_fee,
        tax_amount=order.tax_amount,
        total_amount=order.total_amount,
        advance_amount=order.advance_amount,
        currency=currency,
        payment_method=order.payment_method,
        can_cancel=order.customer_can_cancel,
        payment=payment_read(order.payment, currency) if order.payment else None,
        payments=[payment_read(payment, currency) for payment in order.payments],
        gst=gst_breakdown(order),
        prices_include_gst=order.prices_include_gst,
        tax_review_required=order.tax_review_required,
        delivery_address=delivery_address(order),
        contact_email=order.contact_email,
        is_guest=order.is_guest,
        estimated_delivery_date=order.estimated_delivery_date,
        shipment=shipment_read(order),
        return_reason=order.return_reason,
        return_note=order.return_note,
        created_at=order.created_at,
    )


def order_summary_read(order: Order, currency: str) -> OrderSummaryRead:
    return OrderSummaryRead(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        payment_status=order.payment_status,
        total_amount=order.total_amount,
        currency=currency,
        payment_method=order.payment_method,
        tracking_number=order.tracking_number,
        created_at=order.created_at,
    )


def tracking_read(order: Order, courier: CustomerShipmentRead | None = None) -> OrderTrackingRead:
    return OrderTrackingRead(
        order_number=order.order_number,
        status=order.status,
        estimated_delivery_date=order.estimated_delivery_date,
        shipment=shipment_read(order),
        events=[
            TrackingEventRead(
                status=event.status,
                description=event.description,
                location=event.location,
                source=event.source,
                occurred_at=event.occurred_at,
            )
            for event in order.tracking_events
        ],
        courier=courier,
    )


def invoice_read(order: Order, seller: GstSettings | None, currency: str) -> InvoiceRead:
    """A GST tax invoice built from what the order froze at purchase.

    Line taxes are split the same way checkout split them for classified orders.
    Legacy orders without a frozen GST classification retain their order-level
    tax total, but no tax is assigned to a component or invoice line.
    """
    lines: list[InvoiceLine] = []
    goods_tax = ZERO
    tax_split_known = order.gst_type is not None
    for item in order.items:
        taxable = item.taxable_amount if item.taxable_amount is not None else item.subtotal
        tax = (item.tax_amount or ZERO) if tax_split_known else ZERO
        goods_tax += tax
        if tax_split_known and item.cgst_amount is not None:
            # Frozen at checkout; older lines are split again below.
            cgst, sgst, igst = item.cgst_amount, item.sgst_amount, item.igst_amount
        elif tax_split_known:
            cgst, sgst, igst = split_tax(tax, order.gst_type)
        else:
            cgst, sgst, igst = ZERO, ZERO, ZERO
        lines.append(
            InvoiceLine(
                description=f"{item.product_name} - {item.variant_name}",
                sku=item.sku,
                hsn_code=item.hsn_code,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount=item.discount_amount or ZERO,
                taxable_value=taxable,
                gst_rate=item.gst_rate or ZERO,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total=taxable + tax,
            )
        )

    charges = order.shipping_amount + order.cod_fee
    charges_tax = order.tax_amount - goods_tax if tax_split_known else ZERO
    if charges > ZERO or charges_tax > ZERO:
        cgst, sgst, igst = split_tax(charges_tax, order.gst_type)
        rate = (
            (
                order.charges_gst_rate
                if order.charges_gst_rate is not None
                else money(charges_tax * 100 / charges)
            )
            if charges > ZERO
            else ZERO
        )
        lines.append(
            InvoiceLine(
                description="Shipping and handling" if order.cod_fee else "Shipping charges",
                hsn_code=order.shipping_sac_code or (seller.shipping_sac_code if seller else None),
                quantity=1,
                unit_price=charges,
                discount=ZERO,
                taxable_value=charges,
                gst_rate=rate,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=igst,
                total=charges + charges_tax,
            )
        )

    buyer_code = state_code_for(order.delivery_state)
    address_parts = [
        order.delivery_address_line_1,
        order.delivery_address_line_2,
        order.delivery_city,
        f"{order.delivery_state} {order.delivery_postal_code}",
        order.delivery_country,
    ]
    prefix = order.invoice_prefix or (seller.invoice_prefix if seller else "INV-")
    taxable_value = order.subtotal - order.discount_amount + charges - order.tax_included_amount

    return InvoiceRead(
        invoice_number=f"{prefix}{order.order_number}",
        invoice_date=order.created_at.date(),
        order_number=order.order_number,
        order_status=OrderStatus(order.status),
        gst_type=order.gst_type,
        tax_split_known=tax_split_known,
        place_of_supply=order.place_of_supply,
        seller=InvoiceParty(
            name=order.seller_legal_name or (seller.legal_name if seller else None),
            gstin=(
                order.seller_gstin
                if order.gst_registration_status is not None or not tax_split_known
                else order.seller_gstin or (seller.gstin if seller else None)
            ),
            address=order.seller_address or (seller.address if seller else None),
            state=(order.seller_state or (seller.state if seller else None))
            if tax_split_known
            else None,
            state_code=(order.seller_state_code or (seller.state_code if seller else None))
            if tax_split_known
            else None,
        ),
        buyer=InvoiceParty(
            name=order.delivery_name,
            address=", ".join(part for part in address_parts if part),
            state=order.delivery_state,
            state_code=buyer_code,
        ),
        lines=lines,
        totals=InvoiceTotals(
            subtotal=order.subtotal,
            discount=order.discount_amount,
            shipping=order.shipping_amount,
            cod_fee=order.cod_fee,
            taxable_value=taxable_value,
            cgst_amount=order.cgst_amount if tax_split_known else ZERO,
            sgst_amount=order.sgst_amount if tax_split_known else ZERO,
            igst_amount=order.igst_amount if tax_split_known else ZERO,
            tax_amount=order.tax_amount,
            total=order.total_amount,
        ),
        currency=currency,
    )
