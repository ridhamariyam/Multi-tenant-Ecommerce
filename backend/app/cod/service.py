"""Cash-on-delivery rules: eligibility, fee, advance, blacklist and reporting."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cod.constants import BlacklistSource, CodUnavailableReason
from app.cod.models import CodBlacklistEntry, CodSettings
from app.cod.schemas import BlacklistCreate, CodAvailability, CodSettingsUpdate
from app.core.database import conflict_on_integrity_error
from app.core.exceptions import ConflictError, NotFoundError
from app.core.money import ZERO, money
from app.core.repository import TenantScopedRepository
from app.orders.constants import OrderStatus, PaymentMethod
from app.orders.models import Order
from app.payments.constants import PaymentProvider, PaymentPurpose, PaymentStatus
from app.payments.models import Payment

_MESSAGES = {
    CodUnavailableReason.DISABLED: "Cash on delivery is not available right now",
    CodUnavailableReason.ORDER_TOO_LARGE: (
        "Cash on delivery is not available for orders above {limit}"
    ),
    CodUnavailableReason.ORDER_TOO_SMALL: "Cash on delivery needs an order of at least {limit}",
    CodUnavailableReason.PINCODE_RESTRICTED: (
        "Cash on delivery is not available for this pincode"
    ),
    CodUnavailableReason.PHONE_BLACKLISTED: (
        "Cash on delivery is not available for this phone number. Please pay online."
    ),
}


class CodSettingsRepository(TenantScopedRepository[CodSettings]):
    model = CodSettings

    async def get_for_tenant(self) -> CodSettings | None:
        return await self.session.scalar(self.base_select())


class CodBlacklistRepository(TenantScopedRepository[CodBlacklistEntry]):
    model = CodBlacklistEntry

    async def get_by_phone(self, phone: str) -> CodBlacklistEntry | None:
        return await self.find_one(CodBlacklistEntry.phone == phone)

    async def any_listed(self, phones: list[str]) -> bool:
        if not phones:
            return False
        return await self.find_one(CodBlacklistEntry.phone.in_(phones)) is not None


class CodService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.settings = CodSettingsRepository(session, tenant_id)
        self.blacklist = CodBlacklistRepository(session, tenant_id)

    # --------------------------------------------------------------- settings

    async def get_settings(self) -> CodSettings | None:
        return await self.settings.get_for_tenant()

    async def update_settings(self, data: CodSettingsUpdate) -> CodSettings:
        settings = await self.get_settings()
        values = data.model_dump()
        async with conflict_on_integrity_error(self.session, "Unable to save the COD settings"):
            if settings is None:
                settings = await self.settings.add(CodSettings(**values))
            else:
                for field, value in values.items():
                    setattr(settings, field, value)
            await self.session.commit()

        return settings

    # ------------------------------------------------------------ eligibility

    async def availability(
        self,
        order_value: Decimal,
        *,
        phones: list[str],
        pincode_allows_cod: bool = True,
        currency: str = "",
    ) -> CodAvailability:
        """Can this order be COD? `order_value` is the total before any COD fee."""
        settings = await self.get_settings()
        fee = money(settings.fee_amount) if settings else ZERO

        def unavailable(reason: CodUnavailableReason, limit: Decimal | None = None):
            text = _MESSAGES[reason].format(limit=f"{currency} {limit}".strip())
            return CodAvailability(available=False, reason=reason, message=text, fee=fee)

        if settings is not None:
            if not settings.is_enabled:
                return unavailable(CodUnavailableReason.DISABLED)
            ceiling, floor = settings.max_order_amount, settings.min_order_amount
            if ceiling is not None and order_value > ceiling:
                return unavailable(CodUnavailableReason.ORDER_TOO_LARGE, ceiling)
            if floor is not None and order_value < floor:
                return unavailable(CodUnavailableReason.ORDER_TOO_SMALL, floor)
        if not pincode_allows_cod:
            return unavailable(CodUnavailableReason.PINCODE_RESTRICTED)
        if await self.blacklist.any_listed([p for p in phones if p]):
            return unavailable(CodUnavailableReason.PHONE_BLACKLISTED)

        advance = money(settings.advance_amount) if settings and settings.advance_amount else ZERO
        return CodAvailability(available=True, fee=fee, advance_amount=advance)

    # -------------------------------------------------------------- blacklist

    async def list_blacklist(self, params, *, source: BlacklistSource | None = None):
        stmt = self.blacklist.base_select()
        if source is not None:
            stmt = stmt.where(CodBlacklistEntry.source == source.value)
        rows, total = await self.blacklist.paginate(
            stmt.order_by(CodBlacklistEntry.created_at.desc()), params
        )
        return list(rows), total

    async def add_to_blacklist(
        self,
        data: BlacklistCreate,
        *,
        source: BlacklistSource = BlacklistSource.MANUAL,
        commit: bool = True,
    ) -> CodBlacklistEntry:
        existing = await self.blacklist.get_by_phone(data.phone)
        if existing is not None:
            if commit:
                raise ConflictError("This phone number is already blocked from COD")
            return existing

        entry = await self.blacklist.add(
            CodBlacklistEntry(phone=data.phone, reason=data.reason, source=source.value)
        )
        if commit:
            async with conflict_on_integrity_error(
                self.session,
                "This phone number is already blocked from COD",
            ):
                await self.session.commit()
        return entry

    async def remove_from_blacklist(self, entry_id: UUID) -> None:
        entry = await self.blacklist.get(entry_id)
        if entry is None:
            raise NotFoundError("Blacklist entry not found")
        await self.blacklist.delete(entry)
        await self.session.commit()

    async def auto_blacklist_after_return(self, order, extra_phones=()) -> None:
        """After a RETURNED COD order, block phones that hit the tenant's threshold.

        Runs inside the caller's transaction (no commit of its own).
        """
        settings = await self.get_settings()
        if settings is None or not settings.auto_blacklist_threshold:
            return

        phones = {order.delivery_phone, *[p for p in extra_phones if p]}
        for phone in phones:
            returned = await self.session.scalar(
                select(func.count(Order.id)).where(
                    Order.tenant_id == self.tenant_id,
                    Order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value,
                    Order.status == OrderStatus.RETURNED.value,
                    or_(Order.delivery_phone == phone, Order.customer_id == order.customer_id),
                )
            )
            if (returned or 0) >= settings.auto_blacklist_threshold:
                await self.add_to_blacklist(
                    BlacklistCreate(
                        phone=phone,
                        reason=f"{returned} undelivered COD orders",
                    ),
                    source=BlacklistSource.AUTO,
                    commit=False,
                )

    # ----------------------------------------------------------------- report

    async def report(self, start: date, end: date) -> dict:
        start_dt = datetime.combine(start, time.min, tzinfo=timezone.utc)
        end_dt = datetime.combine(end + timedelta(days=1), time.min, tzinfo=timezone.utc)
        scope = and_(
            Order.tenant_id == self.tenant_id,
            Order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value,
            Order.created_at >= start_dt,
            Order.created_at < end_dt,
        )

        def count_when(*statuses: OrderStatus):
            return func.count(case((Order.status.in_([s.value for s in statuses]), Order.id)))

        def sum_when(column, *statuses: OrderStatus):
            return func.coalesce(
                func.sum(case((Order.status.in_([s.value for s in statuses]), column))), 0
            )

        done = (OrderStatus.DELIVERED, OrderStatus.RETURNED, OrderStatus.CANCELLED)
        in_progress = [s for s in OrderStatus if s not in done]
        row = (
            await self.session.execute(
                select(
                    func.count(Order.id),
                    count_when(OrderStatus.DELIVERED),
                    count_when(OrderStatus.RETURNED),
                    count_when(OrderStatus.CANCELLED),
                    count_when(*in_progress),
                    func.coalesce(func.sum(Order.total_amount), 0),
                    sum_when(Order.total_amount, OrderStatus.DELIVERED),
                    sum_when(Order.total_amount, OrderStatus.RETURNED),
                    sum_when(Order.cod_fee, OrderStatus.DELIVERED),
                ).where(scope)
            )
        ).one()

        async def paid(provider: PaymentProvider, purposes: list[PaymentPurpose]) -> Decimal:
            value = await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount), 0))
                .join(
                    Order,
                    and_(Order.tenant_id == Payment.tenant_id, Order.id == Payment.order_id),
                )
                .where(
                    scope,
                    Payment.status == PaymentStatus.PAID.value,
                    Payment.provider == provider.value,
                    Payment.purpose.in_([p.value for p in purposes]),
                )
            )
            return money(Decimal(value or 0))

        cash = await paid(PaymentProvider.COD, [PaymentPurpose.FULL, PaymentPurpose.BALANCE])
        remitted = money(
            Decimal(
                await self.session.scalar(
                    select(func.coalesce(func.sum(Payment.amount), 0))
                    .join(
                        Order,
                        and_(Order.tenant_id == Payment.tenant_id, Order.id == Payment.order_id),
                    )
                    .where(
                        scope,
                        Payment.status == PaymentStatus.PAID.value,
                        Payment.provider == PaymentProvider.COD.value,
                        Payment.remitted_at.isnot(None),
                    )
                )
                or 0
            )
        )
        advance = await paid(PaymentProvider.PREPAID, [PaymentPurpose.ADVANCE])

        total, delivered, returned, cancelled, progressing = row[:5]
        finished = delivered + returned
        return {
            "start_date": start,
            "end_date": end,
            "total_orders": total,
            "delivered_orders": delivered,
            "returned_orders": returned,
            "cancelled_orders": cancelled,
            "in_progress_orders": progressing,
            "delivery_rate": round(delivered * 100 / finished, 2) if finished else 0.0,
            "order_value": money(Decimal(row[5])),
            "delivered_value": money(Decimal(row[6])),
            "returned_value": money(Decimal(row[7])),
            "cash_collected": cash,
            "advance_collected": advance,
            "fees_collected": money(Decimal(row[8])),
            "net_revenue": cash + advance,
            "cash_remitted": remitted,
            "cash_outstanding": cash - remitted,
        }

    # ------------------------------------------------------------ remittance

    def _collected(self):
        return and_(
            Payment.tenant_id == self.tenant_id,
            Payment.provider == PaymentProvider.COD.value,
            Payment.status == PaymentStatus.PAID.value,
        )

    async def collections(self, params, *, remitted: bool):
        stmt = (
            select(Payment, Order.order_number)
            .join(Order, and_(Order.tenant_id == Payment.tenant_id, Order.id == Payment.order_id))
            .where(
                self._collected(),
                Payment.remitted_at.isnot(None) if remitted else Payment.remitted_at.is_(None),
            )
        )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = (
            await self.session.execute(
                stmt.order_by(Payment.updated_at.desc()).offset(params.offset).limit(params.limit)
            )
        ).all()
        return [
            {
                "payment_id": p.id,
                "order_id": p.order_id,
                "order_number": number,
                "amount": p.amount,
                "collected_at": p.updated_at,
                "remitted_at": p.remitted_at,
                "remittance_reference": p.remittance_reference,
            }
            for p, number in rows
        ], int(total or 0)

    async def record_remittance(
        self, payment_ids: list[UUID], reference: str, remitted_on: date | None
    ) -> dict:
        """Mark collected COD payments as received from the courier."""
        payments = list(
            (
                await self.session.scalars(
                    select(Payment).where(self._collected(), Payment.id.in_(payment_ids))
                )
            ).all()
        )
        found = {p.id for p in payments}
        missing = [str(pid) for pid in payment_ids if pid not in found]
        if missing:
            raise NotFoundError(
                "Not a collected COD payment in this store: " + ", ".join(missing[:5])
            )
        already = [p for p in payments if p.remitted_at is not None]
        if already:
            raise ConflictError(f"{len(already)} payment(s) were already remitted")

        moment = (
            datetime.combine(remitted_on, time.min, tzinfo=timezone.utc)
            if remitted_on
            else datetime.now(timezone.utc)
        )
        for payment in payments:
            payment.remitted_at = moment
            payment.remittance_reference = reference
        await self.session.commit()
        return {
            "remitted": len(payments),
            "amount": money(sum((p.amount for p in payments), ZERO)),
        }
