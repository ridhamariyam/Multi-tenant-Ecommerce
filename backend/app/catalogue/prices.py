"""What a variant costs right now, with a scheduled sale taken into account.

The Python helpers and the SQL expression must agree: listings sort and
filter in SQL, while carts and checkout price in Python.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import and_, case, func, or_

from app.catalogue.models import ProductVariant


def _now() -> datetime:
    return datetime.now(timezone.utc)


def is_on_sale(variant: ProductVariant, at: datetime | None = None) -> bool:
    """A sale price applies only inside its window; open ends are unbounded."""
    if variant.sale_price is None:
        return False

    moment = at or _now()
    if variant.sale_starts_at is not None and moment < variant.sale_starts_at:
        return False
    return variant.sale_ends_at is None or moment < variant.sale_ends_at


def effective_price(variant: ProductVariant, at: datetime | None = None) -> Decimal:
    """The price a shopper pays: the sale price during a sale, else the regular one."""
    return variant.sale_price if is_on_sale(variant, at) else variant.price


def effective_price_sql(entity=ProductVariant):
    """SQL twin of `effective_price` for a ProductVariant class or alias."""
    now = func.now()
    on_sale = and_(
        entity.sale_price.isnot(None),
        or_(entity.sale_starts_at.is_(None), entity.sale_starts_at <= now),
        or_(entity.sale_ends_at.is_(None), entity.sale_ends_at > now),
    )
    return case((on_sale, entity.sale_price), else_=entity.price)
