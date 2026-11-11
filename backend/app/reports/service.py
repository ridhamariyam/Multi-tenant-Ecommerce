"""Admin reports and analytics, computed live from orders, stock and coupons.

Definitions used throughout (so every report agrees):
* An order "counts" when it is not CANCELLED. Its value is `total_amount`.
* RETURNED orders (shipped, came back undelivered) count as orders but are
  reported separately and subtracted for net revenue.
* Dates are order creation dates in UTC; ranges include both end dates.
* Category reports use each product's current category (orders do not
  snapshot categories).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import and_, case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.constants import UserRole
from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import Category, InventoryItem, Product, ProductVariant
from app.catalogue.prices import effective_price_sql
from app.core.money import ZERO, money
from app.coupons.models import Coupon, CouponUsage
from app.orders.constants import OrderStatus, PaymentMethod
from app.orders.models import Order, OrderItem
from app.payments.constants import PaymentPurpose
from app.payments.constants import PaymentStatus as CashStatus
from app.payments.models import Payment
from app.users.models import User

CANCELLED = OrderStatus.CANCELLED.value
RETURNED = OrderStatus.RETURNED.value
DELIVERED = OrderStatus.DELIVERED.value


def day_start(value: date) -> datetime:
    return datetime.combine(value, time.min, tzinfo=timezone.utc)


def _m(value) -> Decimal:
    return money(Decimal(value or 0))


def _pct(part, whole) -> float | None:
    return round(float(part) * 100 / float(whole), 2) if whole else None



NO_REASON = "Not recorded"

class ReportService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _in_range(self, start: date, end: date):
        return and_(
            Order.tenant_id == self.tenant_id,
            Order.created_at >= day_start(start),
            Order.created_at < day_start(end + timedelta(days=1)),
        )

    def _counted(self, start: date, end: date):
        return and_(self._in_range(start, end), Order.status != CANCELLED)

    # ------------------------------------------------------------------ sales

    async def sales(self, start: date, end: date, group_by: str = "day") -> dict:
        bucket = func.date_trunc(group_by, func.timezone("UTC", Order.created_at)).label("bucket")
        returned_value = func.coalesce(
            func.sum(case((Order.status == RETURNED, Order.total_amount))), 0
        )
        stmt = (
            select(
                bucket,
                func.count(case((Order.status != CANCELLED, Order.id))).label("orders"),
                func.count(case((Order.status == CANCELLED, Order.id))).label("cancelled"),
                func.count(case((Order.status == RETURNED, Order.id))).label("returned"),
                func.coalesce(func.sum(case((Order.status != CANCELLED, Order.subtotal))), 0),
                func.coalesce(
                    func.sum(case((Order.status != CANCELLED, Order.discount_amount))), 0
                ),
                func.coalesce(
                    func.sum(case((Order.status != CANCELLED, Order.shipping_amount))), 0
                ),
                func.coalesce(func.sum(case((Order.status != CANCELLED, Order.cod_fee))), 0),
                func.coalesce(func.sum(case((Order.status != CANCELLED, Order.tax_amount))), 0),
                func.coalesce(func.sum(case((Order.status != CANCELLED, Order.total_amount))), 0),
                returned_value,
            )
            .where(self._in_range(start, end))
            .group_by(bucket)
            .order_by(bucket)
        )
        rows = []
        totals = {
            k: ZERO
            for k in (
                "subtotal",
                "discount",
                "shipping",
                "cod_fee",
                "tax",
                "revenue",
                "returned_value",
            )
        }
        counts = {"orders": 0, "cancelled": 0, "returned": 0}
        for row in (await self.session.execute(stmt)).all():
            item = {
                "period": row[0].date(),
                "orders": row[1],
                "cancelled_orders": row[2],
                "returned_orders": row[3],
                "subtotal": _m(row[4]),
                "discount": _m(row[5]),
                "shipping": _m(row[6]),
                "cod_fee": _m(row[7]),
                "tax": _m(row[8]),
                "revenue": _m(row[9]),
                "returned_value": _m(row[10]),
            }
            item["net_revenue"] = item["revenue"] - item["returned_value"]
            item["average_order_value"] = money(item["revenue"] / row[1]) if row[1] else ZERO
            rows.append(item)
            counts["orders"] += row[1]
            counts["cancelled"] += row[2]
            counts["returned"] += row[3]
            for key, src in (
                ("subtotal", "subtotal"),
                ("discount", "discount"),
                ("shipping", "shipping"),
                ("cod_fee", "cod_fee"),
                ("tax", "tax"),
                ("revenue", "revenue"),
                ("returned_value", "returned_value"),
            ):
                totals[key] += item[src]
        summary = {
            "orders": counts["orders"],
            "cancelled_orders": counts["cancelled"],
            "returned_orders": counts["returned"],
            **totals,
            "net_revenue": totals["revenue"] - totals["returned_value"],
            "average_order_value": money(totals["revenue"] / counts["orders"])
            if counts["orders"]
            else ZERO,
        }
        return {"group_by": group_by, "rows": rows, "summary": summary}

    async def sales_by_product(self, start: date, end: date, limit: int = 100) -> list[dict]:
        stmt = (
            select(
                OrderItem.product_id,
                func.max(OrderItem.product_name),
                func.sum(OrderItem.quantity),
                func.count(func.distinct(OrderItem.order_id)),
                func.coalesce(func.sum(OrderItem.subtotal), 0),
                func.coalesce(func.sum(OrderItem.discount_amount), 0),
            )
            .join(
                Order, and_(Order.tenant_id == OrderItem.tenant_id, Order.id == OrderItem.order_id)
            )
            .where(self._counted(start, end))
            .group_by(OrderItem.product_id)
            .order_by(desc(func.coalesce(func.sum(OrderItem.subtotal), 0)), OrderItem.product_id)
            .limit(limit)
        )
        return [
            {
                "product_id": row[0],
                "product_name": row[1],
                "units_sold": int(row[2] or 0),
                "orders": row[3],
                "gross_sales": _m(row[4]),
                "discounts": _m(row[5]),
                "net_sales": _m(row[4]) - _m(row[5]),
            }
            for row in (await self.session.execute(stmt)).all()
        ]

    async def sales_by_category(self, start: date, end: date) -> list[dict]:
        stmt = (
            select(
                Category.id,
                Category.name,
                func.sum(OrderItem.quantity),
                func.count(func.distinct(OrderItem.order_id)),
                func.coalesce(func.sum(OrderItem.subtotal), 0),
                func.coalesce(func.sum(OrderItem.discount_amount), 0),
            )
            .select_from(OrderItem)
            .join(
                Order, and_(Order.tenant_id == OrderItem.tenant_id, Order.id == OrderItem.order_id)
            )
            .join(
                Product,
                and_(Product.tenant_id == OrderItem.tenant_id, Product.id == OrderItem.product_id),
            )
            .join(
                Category,
                and_(Category.tenant_id == Product.tenant_id, Category.id == Product.category_id),
            )
            .where(self._counted(start, end))
            .group_by(Category.id, Category.name)
            .order_by(desc(func.coalesce(func.sum(OrderItem.subtotal), 0)))
        )
        return [
            {
                "category_id": row[0],
                "category_name": row[1],
                "units_sold": int(row[2] or 0),
                "orders": row[3],
                "gross_sales": _m(row[4]),
                "discounts": _m(row[5]),
                "net_sales": _m(row[4]) - _m(row[5]),
            }
            for row in (await self.session.execute(stmt)).all()
        ]

    async def sales_by_location(self, start: date, end: date, level: str = "state") -> list[dict]:
        columns = [func.initcap(func.trim(Order.delivery_state)).label("state")]
        if level == "city":
            columns.append(func.initcap(func.trim(Order.delivery_city)).label("city"))
        stmt = (
            select(
                *columns,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(case((Order.status == RETURNED, Order.id))),
            )
            .where(self._counted(start, end))
            .group_by(*columns)
            .order_by(desc(func.coalesce(func.sum(Order.total_amount), 0)))
        )
        rows = []
        for row in (await self.session.execute(stmt)).all():
            values = list(row)
            item = {"state": values.pop(0)}
            item["city"] = values.pop(0) if level == "city" else None
            item.update(
                {"orders": values[0], "revenue": _m(values[1]), "returned_orders": values[2]}
            )
            rows.append(item)
        return rows

    # -------------------------------------------------------------- inventory

    async def inventory(self, status: str = "all") -> list[dict]:
        sellable = InventoryItem.available_quantity - InventoryItem.reserved_quantity
        stmt = (
            select(
                Product.id,
                Product.name,
                ProductVariant.id,
                ProductVariant.sku,
                ProductVariant.name,
                ProductVariant.status,
                InventoryItem.available_quantity,
                InventoryItem.reserved_quantity,
                sellable,
                InventoryItem.low_stock_threshold,
                effective_price_sql(),
            )
            .select_from(InventoryItem)
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
            .where(
                InventoryItem.tenant_id == self.tenant_id,
                ProductVariant.status != CatalogueStatus.ARCHIVED.value,
            )
            .order_by(sellable, Product.name, ProductVariant.sku)
        )
        if status == "out":
            stmt = stmt.where(sellable <= 0)
        elif status == "low":
            stmt = stmt.where(sellable > 0, sellable <= InventoryItem.low_stock_threshold)
        elif status == "in":
            stmt = stmt.where(sellable > InventoryItem.low_stock_threshold)

        rows = []
        for row in (await self.session.execute(stmt)).all():
            stock = int(row[8])
            rows.append(
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "variant_id": row[2],
                    "sku": row[3],
                    "variant_name": row[4],
                    "variant_status": row[5],
                    "available_quantity": row[6],
                    "reserved_quantity": row[7],
                    "sellable_quantity": stock,
                    "low_stock_threshold": row[9],
                    "stock_status": "OUT_OF_STOCK"
                    if stock <= 0
                    else ("LOW" if stock <= row[9] else "IN_STOCK"),
                    "unit_price": _m(row[10]),
                    "stock_value": _m(row[10] * max(stock, 0)),
                }
            )
        return rows

    async def unsold(self, days: int = 30) -> list[dict]:
        """Live variants with no sale (in a non-cancelled order) in the last `days` days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        last_sold = (
            select(OrderItem.variant_id, func.max(Order.created_at).label("last_sold_at"))
            .join(
                Order, and_(Order.tenant_id == OrderItem.tenant_id, Order.id == OrderItem.order_id)
            )
            .where(OrderItem.tenant_id == self.tenant_id, Order.status != CANCELLED)
            .group_by(OrderItem.variant_id)
            .subquery()
        )
        stmt = (
            select(
                Product.id,
                Product.name,
                ProductVariant.id,
                ProductVariant.sku,
                InventoryItem.available_quantity - InventoryItem.reserved_quantity,
                last_sold.c.last_sold_at,
                ProductVariant.created_at,
            )
            .select_from(ProductVariant)
            .join(
                Product,
                and_(
                    Product.tenant_id == ProductVariant.tenant_id,
                    Product.id == ProductVariant.product_id,
                ),
            )
            .outerjoin(
                InventoryItem,
                and_(
                    InventoryItem.tenant_id == ProductVariant.tenant_id,
                    InventoryItem.variant_id == ProductVariant.id,
                ),
            )
            .outerjoin(last_sold, last_sold.c.variant_id == ProductVariant.id)
            .where(
                ProductVariant.tenant_id == self.tenant_id,
                ProductVariant.status == CatalogueStatus.ACTIVE.value,
                Product.status == CatalogueStatus.ACTIVE.value,
                ProductVariant.created_at < cutoff,
                (last_sold.c.last_sold_at.is_(None)) | (last_sold.c.last_sold_at < cutoff),
            )
            .order_by(last_sold.c.last_sold_at.asc().nulls_first(), Product.name)
        )
        return [
            {
                "product_id": row[0],
                "product_name": row[1],
                "variant_id": row[2],
                "sku": row[3],
                "sellable_quantity": int(row[4] or 0),
                "last_sold_at": row[5],
                "listed_since": row[6],
            }
            for row in (await self.session.execute(stmt)).all()
        ]

    # -------------------------------------------------------------- customers

    async def customers(self, start: date, end: date, top: int = 20) -> dict:
        first_order = (
            select(Order.customer_id, func.min(Order.created_at).label("first_at"))
            .where(Order.tenant_id == self.tenant_id, Order.status != CANCELLED)
            .group_by(Order.customer_id)
            .subquery()
        )
        buyers = (
            select(Order.customer_id)
            .where(self._counted(start, end))
            .group_by(Order.customer_id)
            .subquery()
        )
        split = (
            await self.session.execute(
                select(
                    func.count(case((first_order.c.first_at >= day_start(start), 1))),
                    func.count(case((first_order.c.first_at < day_start(start), 1))),
                )
                .select_from(buyers)
                .join(first_order, first_order.c.customer_id == buyers.c.customer_id)
            )
        ).one()

        signups = await self.session.scalar(
            select(func.count(User.id)).where(
                User.tenant_id == self.tenant_id,
                User.role == UserRole.CUSTOMER.value,
                User.created_at >= day_start(start),
                User.created_at < day_start(end + timedelta(days=1)),
            )
        )

        top_stmt = (
            select(
                User.id,
                User.name,
                User.email,
                User.phone,
                func.count(Order.id),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.max(Order.created_at),
            )
            .join(Order, and_(Order.tenant_id == User.tenant_id, Order.customer_id == User.id))
            .where(self._counted(start, end))
            .group_by(User.id, User.name, User.email, User.phone)
            .order_by(desc(func.coalesce(func.sum(Order.total_amount), 0)), User.id)
            .limit(top)
        )
        top_rows = [
            {
                "customer_id": row[0],
                "name": row[1],
                "email": row[2],
                "phone": row[3],
                "orders": row[4],
                "total_spent": _m(row[5]),
                "last_order_at": row[6],
            }
            for row in (await self.session.execute(top_stmt)).all()
        ]
        new, returning = split
        return {
            "start_date": start,
            "end_date": end,
            "customers_ordering": new + returning,
            "new_customers": new,
            "returning_customers": returning,
            "returning_pct": _pct(returning, new + returning),
            "signups": signups or 0,
            "top_customers": top_rows,
        }

    # ---------------------------------------------------------------- coupons

    async def coupons(self, start: date, end: date) -> list[dict]:
        stmt = (
            select(
                Coupon.id,
                Coupon.code,
                Coupon.discount_type,
                Coupon.is_automatic,
                func.count(CouponUsage.id),
                func.coalesce(func.sum(CouponUsage.discount_amount), 0),
                func.coalesce(func.sum(Order.total_amount), 0),
                func.count(func.distinct(CouponUsage.customer_id)),
            )
            .join(
                CouponUsage,
                and_(CouponUsage.tenant_id == Coupon.tenant_id, CouponUsage.coupon_id == Coupon.id),
            )
            .join(
                Order,
                and_(Order.tenant_id == CouponUsage.tenant_id, Order.id == CouponUsage.order_id),
            )
            .where(self._counted(start, end))
            .group_by(Coupon.id, Coupon.code, Coupon.discount_type, Coupon.is_automatic)
            .order_by(desc(func.count(CouponUsage.id)), Coupon.code)
        )
        return [
            {
                "coupon_id": row[0],
                "code": row[1],
                "discount_type": row[2],
                "is_automatic": row[3],
                "orders": row[4],
                "discount_given": _m(row[5]),
                "order_revenue": _m(row[6]),
                "customers": row[7],
            }
            for row in (await self.session.execute(stmt)).all()
        ]

    # ---------------------------------------------------------------- returns

    async def returns(self, start: date, end: date) -> dict:
        """Undelivered (RETURNED) parcels and cancellations in the range.

        Customer returns/exchanges are not a feature of this backend yet.
        `by_reason` groups returned orders by the reason chosen when they were
        marked RETURNED.
        """
        counts = (
            await self.session.execute(
                select(
                    func.count(case((Order.status == RETURNED, Order.id))),
                    func.coalesce(
                        func.sum(case((Order.status == RETURNED, Order.total_amount))), 0
                    ),
                    func.count(case((Order.status == CANCELLED, Order.id))),
                    func.coalesce(
                        func.sum(case((Order.status == CANCELLED, Order.total_amount))), 0
                    ),
                    func.count(case((Order.status == DELIVERED, Order.id))),
                ).where(self._in_range(start, end))
            )
        ).one()
        by_product = (
            await self.session.execute(
                select(
                    OrderItem.product_id,
                    func.max(OrderItem.product_name),
                    func.sum(OrderItem.quantity),
                    func.count(func.distinct(OrderItem.order_id)),
                )
                .join(
                    Order,
                    and_(Order.tenant_id == OrderItem.tenant_id, Order.id == OrderItem.order_id),
                )
                .where(self._in_range(start, end), Order.status == RETURNED)
                .group_by(OrderItem.product_id)
                .order_by(desc(func.sum(OrderItem.quantity)))
            )
        ).all()
        by_reason = (
            await self.session.execute(
                select(
                    Order.return_reason,
                    func.count(Order.id),
                    func.coalesce(func.sum(Order.total_amount), 0),
                )
                .where(self._in_range(start, end), Order.status == RETURNED)
                .group_by(Order.return_reason)
                .order_by(desc(func.count(Order.id)), Order.return_reason)
            )
        ).all()
        returned, returned_value, cancelled, cancelled_value, delivered = counts
        return {
            "start_date": start,
            "end_date": end,
            "returned_orders": returned,
            "returned_value": _m(returned_value),
            "cancelled_orders": cancelled,
            "cancelled_value": _m(cancelled_value),
            "delivered_orders": delivered,
            "return_rate": _pct(returned, returned + delivered),
            "by_product": [
                {
                    "product_id": row[0],
                    "product_name": row[1],
                    "units_returned": int(row[2] or 0),
                    "orders": row[3],
                }
                for row in by_product
            ],
            "by_reason": [
                {
                    "reason": row[0] or NO_REASON,
                    "orders": row[1],
                    "returned_value": _m(row[2]),
                }
                for row in by_reason
            ],
        }

    # -------------------------------------------------------------- analytics

    async def analytics(self, start: date, end: date) -> dict:
        row = (
            await self.session.execute(
                select(
                    func.count(case((Order.status != CANCELLED, Order.id))),
                    func.coalesce(
                        func.sum(case((Order.status != CANCELLED, Order.total_amount))), 0
                    ),
                    func.count(case((Order.status == CANCELLED, Order.id))),
                    func.count(case((Order.status == RETURNED, Order.id))),
                    func.count(case((Order.status == DELIVERED, Order.id))),
                    func.count(Order.id),
                    func.count(
                        case(
                            (
                                and_(
                                    Order.status != CANCELLED,
                                    Order.payment_method == PaymentMethod.CASH_ON_DELIVERY.value,
                                ),
                                Order.id,
                            )
                        )
                    ),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    and_(
                                        Order.status != CANCELLED,
                                        Order.payment_method
                                        == PaymentMethod.CASH_ON_DELIVERY.value,
                                    ),
                                    Order.total_amount,
                                )
                            )
                        ),
                        0,
                    ),
                ).where(self._in_range(start, end))
            )
        ).one()
        orders, revenue, cancelled, returned, delivered, placed, cod_orders, cod_revenue = row
        revenue = _m(revenue)
        cod_revenue = _m(cod_revenue)
        customers = await self.customers(start, end, top=0)
        return {
            "start_date": start,
            "end_date": end,
            "orders": orders,
            "revenue": revenue,
            "average_order_value": money(revenue / orders) if orders else ZERO,
            "cancelled_orders": cancelled,
            "cancellation_rate": _pct(cancelled, placed),
            "returned_orders": returned,
            "return_rate": _pct(returned, returned + delivered),
            "cod_orders": cod_orders,
            "cod_revenue": cod_revenue,
            "prepaid_orders": orders - cod_orders,
            "prepaid_revenue": revenue - cod_revenue,
            "cod_share_pct": _pct(cod_orders, orders),
            "new_customers": customers["new_customers"],
            "returning_customers": customers["returning_customers"],
            "top_products": await self.sales_by_product(start, end, limit=10),
        }

    # -------------------------------------------------------------- dashboard

    async def attention(self) -> dict:
        """Orders a person needs to act on now."""
        counts = dict(
            (
                await self.session.execute(
                    select(Order.status, func.count(Order.id))
                    .where(
                        Order.tenant_id == self.tenant_id,
                        Order.status.in_(
                            [
                                OrderStatus.PENDING.value,
                                OrderStatus.CONFIRMED.value,
                                OrderStatus.PROCESSING.value,
                                OrderStatus.PACKED.value,
                                OrderStatus.SHIPPED.value,
                                OrderStatus.OUT_FOR_DELIVERY.value,
                            ]
                        ),
                    )
                    .group_by(Order.status)
                )
            ).all()
        )
        advance_pending = await self.session.scalar(
            select(func.count(func.distinct(Order.id)))
            .join(Payment, and_(Payment.tenant_id == Order.tenant_id, Payment.order_id == Order.id))
            .where(
                Order.tenant_id == self.tenant_id,
                Order.status == OrderStatus.PENDING.value,
                Payment.purpose == PaymentPurpose.ADVANCE.value,
                Payment.status == CashStatus.PENDING.value,
            )
        )
        return {
            "new_orders": counts.get(OrderStatus.PENDING.value, 0),
            "awaiting_packing": counts.get(OrderStatus.CONFIRMED.value, 0)
            + counts.get(OrderStatus.PROCESSING.value, 0),
            "awaiting_shipment": counts.get(OrderStatus.PACKED.value, 0),
            "in_transit": counts.get(OrderStatus.SHIPPED.value, 0)
            + counts.get(OrderStatus.OUT_FOR_DELIVERY.value, 0),
            "advance_pending": advance_pending or 0,
        }

    async def day_comparison(self) -> dict:
        """Today so far vs yesterday and vs the same weekday last week (orders placed)."""
        today = datetime.now(timezone.utc).date()

        async def stats(day: date) -> tuple[int, Decimal]:
            row = (
                await self.session.execute(
                    select(
                        func.count(Order.id), func.coalesce(func.sum(Order.total_amount), 0)
                    ).where(self._counted(day, day))
                )
            ).one()
            return row[0], _m(row[1])

        now_orders, now_revenue = await stats(today)
        y_orders, y_revenue = await stats(today - timedelta(days=1))
        w_orders, w_revenue = await stats(today - timedelta(days=7))

        def change(cur, prev):
            return round((float(cur) - float(prev)) * 100 / float(prev), 2) if prev else None

        return {
            "today_orders": now_orders,
            "today_revenue": now_revenue,
            "yesterday_orders": y_orders,
            "yesterday_revenue": y_revenue,
            "last_week_orders": w_orders,
            "last_week_revenue": w_revenue,
            "orders_vs_yesterday_pct": change(now_orders, y_orders),
            "revenue_vs_yesterday_pct": change(now_revenue, y_revenue),
            "orders_vs_last_week_pct": change(now_orders, w_orders),
            "revenue_vs_last_week_pct": change(now_revenue, w_revenue),
        }
