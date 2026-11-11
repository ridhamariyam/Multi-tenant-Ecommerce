"""Write every successful order to the brand's Google Sheet, once.

An order counts once it is a sale: cash on delivery with nothing to pay
upfront is a sale when placed; an online order (or a COD order with an
advance) once its money is captured. Cancelled orders that never got there
are left out.

Exporting runs in the background (app.commands.sync_order_sheets), never in
checkout, so a slow or failing Google never holds up an order. Each exported
order is recorded, so a run that fails is simply picked up by the next one.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, exists, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.error_codes import IntegrationErrorCode
from app.core.exceptions import ServiceUnavailableError, ValidationError
from app.integrations import google_sheets
from app.integrations.google_sheets import SheetsClient, SheetsError
from app.integrations.models import (
    DEFAULT_WORKSHEET_NAME,
    OrderSheetExport,
    OrderSheetSettings,
)
from app.orders.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.orders.models import Order

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30), "IST")

HEADER = [
    "Order Number",
    "Placed At (IST)",
    "Order Status",
    "Payment Method",
    "Payment Status",
    "Deliver To",
    "Delivery Phone",
    "Email",
    "Address",
    "City",
    "State",
    "Pincode",
    "Items",
    "Quantity",
    "Subtotal",
    "Discount",
    "Coupon",
    "Shipping",
    "COD Fee",
    "Tax",
    "Total",
    "Advance Paid",
    "Guest Checkout",
]

PAYMENT_METHOD_LABELS = {
    PaymentMethod.UPI.value: "UPI",
    PaymentMethod.CREDIT_CARD.value: "Credit card",
    PaymentMethod.DEBIT_CARD.value: "Debit card",
    PaymentMethod.NET_BANKING.value: "Net banking",
    PaymentMethod.CASH_ON_DELIVERY.value: "Cash on delivery",
}


def is_sale():
    """SQL: the order has become a sale (see the module docstring)."""
    return and_(
        Order.status != OrderStatus.CANCELLED.value,
        or_(
            and_(
                Order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value,
                Order.advance_amount == 0,
            ),
            Order.payment_status.in_(
                [PaymentStatus.PAID.value, PaymentStatus.PARTIALLY_PAID.value]
            ),
        ),
    )


def _label(value: str) -> str:
    return value.replace("_", " ").capitalize()


def _amount(value: Decimal | None) -> float:
    return float(value or 0)


def order_row(order: Order) -> list[Any]:
    """One sheet row; numbers stay numbers so the sheet can total them."""
    items = "; ".join(
        f"{item.product_name}"
        + (f" ({item.variant_name})" if item.variant_name else "")
        + (f" [{item.sku}]" if item.sku else "")
        + f" x {item.quantity}"
        for item in order.items
    )
    address = ", ".join(
        part for part in (order.delivery_address_line_1, order.delivery_address_line_2) if part
    )
    advance_paid = (
        _amount(order.advance_amount)
        if order.payment_status
        in (PaymentStatus.PAID.value, PaymentStatus.PARTIALLY_PAID.value)
        and order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value
        else 0.0
    )
    return [
        order.order_number,
        order.created_at.astimezone(IST).strftime("%Y-%m-%d %H:%M"),
        _label(order.status),
        PAYMENT_METHOD_LABELS.get(order.payment_method, _label(order.payment_method)),
        _label(order.payment_status),
        order.delivery_name,
        order.delivery_phone,
        order.contact_email or "",
        address,
        order.delivery_city,
        order.delivery_state,
        order.delivery_postal_code,
        items,
        sum(item.quantity for item in order.items),
        _amount(order.subtotal),
        _amount(order.discount_amount),
        order.coupon_code or "",
        _amount(order.shipping_amount),
        _amount(order.cod_fee),
        _amount(order.tax_amount),
        _amount(order.total_amount),
        advance_paid,
        "Yes" if order.is_guest else "No",
    ]


def _invalid_tab_name(name: str) -> bool:
    return any(ch in name for ch in "[]*?/\\:")


@dataclass
class SyncResult:
    exported: int
    pending: int
    error: str | None = None


def _error_code(error: SheetsError):
    return {
        "not_configured": IntegrationErrorCode.SHEETS_NOT_CONFIGURED,
        "access_denied": IntegrationErrorCode.SHEETS_ACCESS_DENIED,
        "not_found": IntegrationErrorCode.SHEETS_NOT_FOUND,
    }.get(error.kind, IntegrationErrorCode.SHEETS_UNAVAILABLE)


class OrderSheetService:
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    # ------------------------------------------------------------ settings

    async def get_settings(self) -> OrderSheetSettings:
        """The stored settings, or unsaved defaults (off, no sheet)."""
        found = await self.session.scalar(
            select(OrderSheetSettings).where(OrderSheetSettings.tenant_id == self.tenant_id)
        )
        if found is not None:
            return found
        return OrderSheetSettings(
            tenant_id=self.tenant_id, is_enabled=False, worksheet_name=DEFAULT_WORKSHEET_NAME
        )

    async def update_settings(
        self,
        *,
        is_enabled: bool,
        spreadsheet: str | None,
        worksheet_name: str,
        user_id: uuid.UUID | None,
    ) -> OrderSheetSettings:
        worksheet_name = worksheet_name.strip() or DEFAULT_WORKSHEET_NAME
        if _invalid_tab_name(worksheet_name):
            raise ValidationError(
                "A tab name cannot contain [ ] * ? / \\ or :",
                details=[{"field": "worksheet_name", "message": "Invalid tab name"}],
            )

        spreadsheet_id: str | None = None
        if spreadsheet and spreadsheet.strip():
            spreadsheet_id = google_sheets.parse_spreadsheet_id(spreadsheet)
            if spreadsheet_id is None:
                raise ValidationError(
                    "Paste the spreadsheet's link (docs.google.com/spreadsheets/d/...) or its ID.",
                    error_code=IntegrationErrorCode.SHEETS_INVALID_SPREADSHEET,
                    details=[{"field": "spreadsheet", "message": "Not a Google Sheets link or ID"}],
                )

        if is_enabled:
            if spreadsheet_id is None:
                raise ValidationError(
                    "Add the spreadsheet before turning the export on.",
                    error_code=IntegrationErrorCode.SHEETS_INVALID_SPREADSHEET,
                    details=[{"field": "spreadsheet", "message": "Required to turn the export on"}],
                )
            # Proves access now, and leaves the tab with its header row ready.
            await self._verify(spreadsheet_id, worksheet_name)

        settings = await self.get_settings()
        settings.is_enabled = is_enabled
        settings.spreadsheet_id = spreadsheet_id
        settings.worksheet_name = worksheet_name
        settings.updated_by_id = user_id
        settings.last_error = None
        settings.last_error_at = None
        self.session.add(settings)
        await self.session.commit()
        await self.session.refresh(settings)
        return settings

    async def _verify(self, spreadsheet_id: str, worksheet_name: str) -> None:
        try:
            await SheetsClient(spreadsheet_id).ensure_worksheet(worksheet_name, HEADER)
        except SheetsError as error:
            cls = ServiceUnavailableError if error.kind in ("unavailable", "not_configured") else ValidationError
            raise cls(
                error.message,
                error_code=_error_code(error),
                details=[{"field": "spreadsheet", "message": error.message}]
                if cls is ValidationError
                else None,
            ) from error

    # -------------------------------------------------------------- counts

    def _not_exported(self, spreadsheet_id: str):
        return ~exists().where(
            OrderSheetExport.order_id == Order.id,
            OrderSheetExport.spreadsheet_id == spreadsheet_id,
        )

    async def counts(self, settings: OrderSheetSettings) -> tuple[int, int]:
        """(waiting to be exported, already in the sheet) for the current spreadsheet."""
        if not settings.spreadsheet_id:
            return 0, 0
        pending = await self.session.scalar(
            select(func.count(Order.id)).where(
                Order.tenant_id == self.tenant_id,
                is_sale(),
                self._not_exported(settings.spreadsheet_id),
            )
        )
        exported = await self.session.scalar(
            select(func.count(OrderSheetExport.id)).where(
                OrderSheetExport.tenant_id == self.tenant_id,
                OrderSheetExport.spreadsheet_id == settings.spreadsheet_id,
            )
        )
        return int(pending or 0), int(exported or 0)

    # ---------------------------------------------------------------- sync

    async def sync(self) -> SyncResult:
        """Append every sale not yet in the sheet. Never raises for Google failures."""
        settings = await self.get_settings()
        if not settings.is_enabled or not settings.spreadsheet_id or settings.id is None:
            return SyncResult(exported=0, pending=0)
        spreadsheet_id = settings.spreadsheet_id
        worksheet = settings.worksheet_name
        settings_id = settings.id
        await self.session.commit()

        client = SheetsClient(spreadsheet_id)
        batch_size = get_settings().order_sheet_batch_size
        exported = 0
        error: str | None = None
        header_checked = False

        while True:
            # One exporter per brand at a time; a second run just stops here.
            locked = await self.session.scalar(
                text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"),
                {"key": f"order_sheets:{self.tenant_id}"},
            )
            if not locked:
                await self.session.rollback()
                break

            orders = (
                await self.session.scalars(
                    select(Order)
                    .where(
                        Order.tenant_id == self.tenant_id,
                        is_sale(),
                        self._not_exported(spreadsheet_id),
                    )
                    .order_by(Order.created_at, Order.id)
                    .limit(batch_size)
                )
            ).all()
            if not orders:
                await self.session.rollback()
                break

            try:
                if not header_checked:
                    await client.ensure_worksheet(worksheet, HEADER)
                    header_checked = True
                await client.append_rows(worksheet, [order_row(order) for order in orders])
            except SheetsError as exc:
                await self.session.rollback()
                error = exc.message
                logger.warning("Order sheet export failed for tenant %s: %s", self.tenant_id, exc)
                break

            now = datetime.now(timezone.utc)
            for order in orders:
                self.session.add(
                    OrderSheetExport(
                        tenant_id=self.tenant_id,
                        order_id=order.id,
                        spreadsheet_id=spreadsheet_id,
                        exported_at=now,
                    )
                )
            await self.session.commit()
            exported += len(orders)
            if len(orders) < batch_size:
                break

        await self._record_outcome(settings_id, error)
        settings = await self.get_settings()
        pending, _ = await self.counts(settings)
        return SyncResult(exported=exported, pending=pending, error=error)

    async def _record_outcome(self, settings_id: uuid.UUID, error: str | None) -> None:
        settings = await self.session.get(OrderSheetSettings, settings_id)
        if settings is None:
            return
        now = datetime.now(timezone.utc)
        if error:
            settings.last_error = error[:500]
            settings.last_error_at = now
        else:
            settings.last_synced_at = now
            settings.last_error = None
            settings.last_error_at = None
        await self.session.commit()
