from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.catalogue.models import InventoryItem, Product, ProductVariant
from app.core.money import money
from app.orders.constants import FULFILMENT_STATUSES, OrderStatus
from app.orders.constants import PaymentStatus as OrderPaymentStatus
from app.orders.models import Order, OrderItem
from app.payments.constants import PaymentStatus
from app.payments.models import Payment
from app.users.models import User

# low_stock_threshold is NOT NULL default 0, so an unset one reads as 0.
DEFAULT_LOW_STOCK_THRESHOLD = 5

# How many example variants the overview carries alongside the counts.
STOCK_SAMPLE_SIZE = 10


class DashboardService:
    """Aggregates multi-tenant business data for the admin dashboard."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _calculate_change_pct(
        self,
        current: Decimal | int,
        previous: Decimal | int,
    ) -> float | None:
        if previous == 0:
            return None

        diff = float(current) - float(previous)
        return round((diff / float(previous)) * 100.0, 2)

    async def get_overview(self, currency: str = "USD") -> dict:
        now_utc = datetime.now(timezone.utc)
        today_start = datetime.combine(
            now_utc.date(),
            time.min,
            tzinfo=timezone.utc,
        )
        week_start = today_start - timedelta(days=7)
        month_start = datetime.combine(
            now_utc.date().replace(day=1),
            time.min,
            tzinfo=timezone.utc,
        )

        yesterday_start = today_start - timedelta(days=1)
        prev_month_start = (month_start - timedelta(days=1)).replace(day=1)

        async def get_sales_stats(
            start_dt: datetime,
            end_dt: datetime,
        ) -> tuple[int, Decimal]:
            stmt = select(
                func.count(Order.id),
                func.coalesce(
                    func.sum(Order.total_amount),
                    Decimal("0.00"),
                ),
            ).where(
                Order.tenant_id == self.tenant_id,
                Order.created_at >= start_dt,
                Order.created_at < end_dt,
                Order.status.in_(FULFILMENT_STATUSES),
                Order.payment_status == OrderPaymentStatus.PAID.value,
            )

            res = (await self.session.execute(stmt)).one()
            return res[0], money(res[1])

        today_orders, today_rev = await get_sales_stats(
            today_start,
            now_utc,
        )
        yest_orders, yest_rev = await get_sales_stats(
            yesterday_start,
            today_start,
        )

        week_orders, week_rev = await get_sales_stats(
            week_start,
            now_utc,
        )
        prev_week_start = week_start - timedelta(days=7)
        prev_week_orders, prev_week_rev = await get_sales_stats(
            prev_week_start,
            week_start,
        )

        month_orders, month_rev = await get_sales_stats(
            month_start,
            now_utc,
        )
        prev_month_orders, prev_month_rev = await get_sales_stats(
            prev_month_start,
            month_start,
        )

        total_stmt = select(
            func.count(Order.id),
            func.coalesce(
                func.sum(Order.total_amount),
                Decimal("0.00"),
            ),
        ).where(
            Order.tenant_id == self.tenant_id,
            Order.status.in_(FULFILMENT_STATUSES),
            Order.payment_status == OrderPaymentStatus.PAID.value,
        )

        total_res = (await self.session.execute(total_stmt)).one()
        total_order_count, total_revenue = total_res[0], money(total_res[1])

        sales_overview = {
            "today": {
                "order_count": today_orders,
                "revenue": today_rev,
                "previous_order_count": yest_orders,
                "previous_revenue": yest_rev,
                "order_count_change_pct": self._calculate_change_pct(
                    today_orders,
                    yest_orders,
                ),
                "revenue_change_pct": self._calculate_change_pct(
                    today_rev,
                    yest_rev,
                ),
            },
            "week": {
                "order_count": week_orders,
                "revenue": week_rev,
                "previous_order_count": prev_week_orders,
                "previous_revenue": prev_week_rev,
                "order_count_change_pct": self._calculate_change_pct(
                    week_orders,
                    prev_week_orders,
                ),
                "revenue_change_pct": self._calculate_change_pct(
                    week_rev,
                    prev_week_rev,
                ),
            },
            "month": {
                "order_count": month_orders,
                "revenue": month_rev,
                "previous_order_count": prev_month_orders,
                "previous_revenue": prev_month_rev,
                "order_count_change_pct": self._calculate_change_pct(
                    month_orders,
                    prev_month_orders,
                ),
                "revenue_change_pct": self._calculate_change_pct(
                    month_rev,
                    prev_month_rev,
                ),
            },
            "total_order_count": total_order_count,
            "total_revenue": total_revenue,
        }

        # Order Status Breakdown
        status_stmt = select(
            Order.status,
            func.count(Order.id),
        ).where(
            Order.tenant_id == self.tenant_id,
        ).group_by(Order.status)

        status_counts = {
            row[0]: row[1]
            for row in (await self.session.execute(status_stmt)).all()
        }

        # All orders regardless of status -- distinct from sales.total_order_count,
        # which only counts completed (processing/shipped/delivered) orders.
        total_orders_count = (
            await self.session.scalar(
                select(func.count(Order.id)).where(
                    Order.tenant_id == self.tenant_id,
                )
            )
        ) or 0

        # Today's Orders -- every order created today, any status. Distinct
        # from sales.today.order_count, which only counts completed sales.
        today_orders_count = (
            await self.session.scalar(
                select(func.count(Order.id)).where(
                    Order.tenant_id == self.tenant_id,
                    Order.created_at >= today_start,
                    Order.created_at < now_utc,
                )
            )
        ) or 0

        # A "returned order" is one whose payment was refunded, or a parcel
        # that came back undelivered (RETURNED status).
        returned_orders_count = (
            await self.session.scalar(
                select(func.count(func.distinct(Order.id)))
                .select_from(Order)
                .join(
                    Payment,
                    and_(
                        Payment.tenant_id == Order.tenant_id,
                        Payment.order_id == Order.id,
                    ),
                )
                .where(
                    Order.tenant_id == self.tenant_id,
                    or_(
                        Payment.status == PaymentStatus.REFUNDED,
                        Order.status == OrderStatus.RETURNED,
                    ),
                )
            )
        ) or 0

        orders_summary = {
            "total": total_orders_count,
            "today": today_orders_count,
            "pending": status_counts.get(OrderStatus.PENDING, 0),
            "processing": status_counts.get(OrderStatus.PROCESSING, 0),
            "shipped": status_counts.get(OrderStatus.SHIPPED, 0),
            "delivered": status_counts.get(OrderStatus.DELIVERED, 0),
            "cancelled": status_counts.get(OrderStatus.CANCELLED, 0),
            "returned": returned_orders_count,
            "other": sum(
                v
                for k, v in status_counts.items()
                if k not in {s.value for s in OrderStatus}
            ),
        }

        # Total Products
        total_products_count = (
            await self.session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == self.tenant_id,
                )
            )
        ) or 0

        products_overview = {"total": total_products_count}

        # Inventory Overview. Filtered and counted in SQL -- pulling every
        # variant into Python to slice ten of them does not survive a real
        # catalogue.
        sellable = InventoryItem.available_quantity - InventoryItem.reserved_quantity
        # The column is NOT NULL default 0, so 0 is what "nobody set one"
        # looks like. Treating it as the default preserves the alerting admins
        # already get; making 0 mean "never warn" is a product decision.
        threshold = case(
            (
                InventoryItem.low_stock_threshold > 0,
                InventoryItem.low_stock_threshold,
            ),
            else_=DEFAULT_LOW_STOCK_THRESHOLD,
        )

        def _stock_select(*conditions):
            return (
                select(
                    Product.id.label("product_id"),
                    Product.name.label("product_name"),
                    ProductVariant.id.label("variant_id"),
                    ProductVariant.sku.label("sku"),
                    sellable.label("available_quantity"),
                    threshold.label("low_stock_threshold"),
                )
                .join(
                    ProductVariant,
                    and_(
                        ProductVariant.tenant_id == InventoryItem.tenant_id,
                        ProductVariant.id == InventoryItem.variant_id,
                    ),
                )
                .join(
                    Product,
                    and_(
                        Product.tenant_id == ProductVariant.tenant_id,
                        Product.id == ProductVariant.product_id,
                    ),
                )
                .select_from(InventoryItem)
                .where(InventoryItem.tenant_id == self.tenant_id, *conditions)
            )

        out_of_stock = _stock_select(sellable <= 0)
        low_stock = _stock_select(sellable > 0, sellable <= threshold)

        async def _count(stmt) -> int:
            return int(
                await self.session.scalar(
                    select(func.count()).select_from(stmt.subquery())
                )
                or 0
            )

        inventory_overview = {
            "low_stock_count": await _count(low_stock),
            "out_of_stock_count": await _count(out_of_stock),
            "low_stock_variants": [
                dict(row._mapping)
                for row in (
                    await self.session.execute(
                        low_stock.order_by(sellable).limit(STOCK_SAMPLE_SIZE)
                    )
                ).all()
            ],
            "out_of_stock_variants": [
                dict(row._mapping)
                for row in (
                    await self.session.execute(
                        out_of_stock.order_by(ProductVariant.sku).limit(STOCK_SAMPLE_SIZE)
                    )
                ).all()
            ],
        }

        # Customer Overview
        cust_base = select(func.count(User.id)).where(
            User.tenant_id == self.tenant_id,
            User.role == UserRole.CUSTOMER.value,
        )

        total_customers = (await self.session.scalar(cust_base)) or 0
        new_today_cust = (
            await self.session.scalar(
                cust_base.where(User.created_at >= today_start)
            )
        ) or 0
        new_month_cust = (
            await self.session.scalar(
                cust_base.where(User.created_at >= month_start)
            )
        ) or 0

        customer_overview = {
            "total": total_customers,
            "new_today": new_today_cust,
            "new_this_month": new_month_cust,
        }

        # Payment Overview
        pay_stmt = select(
            Payment.status,
            func.count(Payment.id),
        ).where(
            Payment.tenant_id == self.tenant_id,
        ).group_by(Payment.status)

        pay_counts = {
            row[0]: row[1]
            for row in (await self.session.execute(pay_stmt)).all()
        }

        today_paid_amount = (
            await self.session.scalar(select(func.coalesce(
                        func.sum(Payment.amount),
                        Decimal("0.00"),
                    )
                ).where(
                    Payment.tenant_id == self.tenant_id,
                    Payment.status == PaymentStatus.PAID,
                    Payment.created_at >= today_start,
                )
            )
        ) or Decimal("0.00")

        payment_overview = {
            "paid_count": pay_counts.get(PaymentStatus.PAID, 0),
            "pending_count": pay_counts.get(PaymentStatus.PENDING, 0),
            "failed_count": pay_counts.get(PaymentStatus.FAILED, 0),
            "refunded_count": pay_counts.get(PaymentStatus.REFUNDED, 0),
            "today_paid_amount": money(today_paid_amount),
        }

        # Recent Orders
        recent_stmt = (
            select(Order, User)
            .outerjoin(
                User,
                and_(
                    Order.customer_id == User.id,
                    Order.tenant_id == User.tenant_id,
                ),
            )
            .where(
                Order.tenant_id == self.tenant_id,
            )
            .order_by(
                Order.created_at.desc(),
            )
            .limit(5)
        )

        recent_rows = (await self.session.execute(recent_stmt)).all()

        recent_orders = []

        for ord_obj, usr_obj in recent_rows:
            recent_orders.append(
                {
                    "order_id": ord_obj.id,
                    "order_number": ord_obj.order_number,
                    "customer_email": usr_obj.email if usr_obj else None,
                    "total_amount": ord_obj.total_amount,
                    "currency": currency,
                    "order_status": ord_obj.status,
                    "payment_status": ord_obj.payment_status,
                    "created_at": ord_obj.created_at,
                }
            )

        return {
            "sales": sales_overview,
            "orders": orders_summary,
            "products": products_overview,
            "inventory": inventory_overview,
            "customers": customer_overview,
            "payments": payment_overview,
            "recent_orders": recent_orders,
        }

    async def get_sales_trend(self, days: int = 30) -> list[dict]:
        start_date = (
            datetime.now(timezone.utc).date() - timedelta(days=days)
        )
        completed_statuses = list(FULFILMENT_STATUSES)

        stmt = (
            select(
                func.date(Order.created_at).label("order_date"),
                func.count(Order.id).label("order_count"),
                func.coalesce(
                    func.sum(Order.total_amount),
                    Decimal("0.00"),
                ).label("revenue"),
            )
            .where(
                Order.tenant_id == self.tenant_id,
                func.date(Order.created_at) >= start_date,
                Order.status.in_(completed_statuses),
            )
            .group_by(
                func.date(Order.created_at),
            )
            .order_by(
                func.date(Order.created_at).asc(),
            )
        )

        rows = (await self.session.execute(stmt)).all()

        return [
            {
                "date": row.order_date,
                "order_count": row.order_count,
                "revenue": money(row.revenue),
            }
            for row in rows
        ]

    async def get_top_products(
        self,
        days: int = 30,
        limit: int = 10,
    ) -> list[dict]:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        completed_statuses = list(FULFILMENT_STATUSES)

        stmt = (
            select(
                Product.id,
                Product.name,
                func.sum(OrderItem.quantity).label("quantity_sold"),
                func.coalesce(
                    func.sum(OrderItem.subtotal),
                    Decimal("0.00"),
                ).label("revenue_generated"),
            )
            .join(
                ProductVariant,
                and_(
                    ProductVariant.tenant_id == OrderItem.tenant_id,
                    ProductVariant.id == OrderItem.variant_id,
                ),
            )
            .join(
                Product,
                and_(
                    Product.tenant_id == ProductVariant.tenant_id,
                    Product.id == ProductVariant.product_id,
                ),
            )
            .join(
                Order,
                and_(
                    Order.tenant_id == OrderItem.tenant_id,
                    Order.id == OrderItem.order_id,
                ),
            )
            .where(
                Order.tenant_id == self.tenant_id,
                Order.created_at >= start_date,
                Order.status.in_(completed_statuses),
            )
            .group_by(
                Product.id,
                Product.name,
            )
            .order_by(
                desc("quantity_sold"),
            )
            .limit(limit)
        )

        rows = (await self.session.execute(stmt)).all()

        return [
            {
                "product_id": row.id,
                "product_name": row.name,
                "quantity_sold": row.quantity_sold,
                "revenue_generated": money(row.revenue_generated),
            }
            for row in rows
        ]
