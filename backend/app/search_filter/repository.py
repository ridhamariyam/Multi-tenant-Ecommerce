from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, case, delete, desc, exists, func, or_, select, union
from sqlalchemy.orm import aliased, selectinload

from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import (
    Category,
    Product,
    ProductOption,
    ProductVariant,
    ProductVariantOption,
)
from app.catalogue.prices import effective_price_sql
from app.catalogue.repository import attribute_matches, category_subtree
from app.core.pagination import PageParams
from app.core.repository import TenantScopedRepository, escape_like
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem
from app.ratings.models import Review
from app.search_filter.constants import (
    COLOR_OPTION,
    MAX_HISTORY_ENTRIES,
    MAX_SUGGESTIONS,
    SIZE_OPTION,
    SearchSort,
)
from app.search_filter.models import SearchHistory
from app.search_filter.schemas import ProductFilters

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")

DiscoveryRow = tuple[Product, Decimal | None, Decimal | None, float | None]


def tokenize(query: str) -> list[str]:
    """Words a query is matched by; apostrophes are dropped, as they are in the data."""
    return _TOKEN_PATTERN.findall(query.replace("'", ""))


class SearchFilterRepository(TenantScopedRepository[SearchHistory]):
    model = SearchHistory

    @staticmethod
    def _option_matches(variant, option_name: str, value: str):
        """Build a case-insensitive variant option predicate."""
        return variant.option_values.any(
            and_(
                func.lower(ProductVariantOption.value) == value.lower(),
                ProductVariantOption.option.has(
                    func.lower(ProductOption.name) == option_name.lower()
                ),
            )
        )

    def _has_matching_variant(self, filters: ProductFilters):
        """One live variant must satisfy every variant-level filter at once.

        An EXISTS rather than a narrowed join: the join feeds min()/max(), so
        filtering it would make the reported price range describe the surviving
        variants instead of the product the card is for.
        """
        variant = aliased(ProductVariant)

        conditions = []
        if filters.min_price is not None:
            conditions.append(effective_price_sql(variant) >= filters.min_price)
        if filters.max_price is not None:
            conditions.append(effective_price_sql(variant) <= filters.max_price)
        if filters.color:
            conditions.append(
                self._option_matches(variant, COLOR_OPTION, filters.color)
            )
        if filters.size:
            conditions.append(self._option_matches(variant, SIZE_OPTION, filters.size))

        if not conditions:
            return None

        return (
            select(1)
            .where(
                variant.tenant_id == Product.tenant_id,
                variant.product_id == Product.id,
                variant.status == CatalogueStatus.ACTIVE.value,
                *conditions,
            )
            .correlate(Product)
            .exists()
        )

    @staticmethod
    def _token_matches(token: str):
        """Build a predicate for a searchable product token."""
        pattern = f"%{escape_like(token)}%"

        def _clean(column):
            return func.replace(column, "'", "")

        return or_(
            _clean(Product.name).ilike(pattern, escape="\\"),
            _clean(Product.brand).ilike(pattern, escape="\\"),
            _clean(Product.short_description).ilike(pattern, escape="\\"),
            _clean(Product.description).ilike(pattern, escape="\\"),
            _clean(Product.fabric).ilike(pattern, escape="\\"),
            _clean(Product.occasion).ilike(pattern, escape="\\"),
            _clean(Product.sleeve).ilike(pattern, escape="\\"),
            _clean(Product.neckline).ilike(pattern, escape="\\"),
            _clean(ProductVariant.sku).ilike(pattern, escape="\\"),
            _clean(Product.gender).ilike(pattern, escape="\\"),
            exists(
                select(1).where(
                    Category.tenant_id == Product.tenant_id,
                    Category.id == Product.category_id,
                    func.replace(Category.name, "'", "").ilike(pattern, escape="\\"),
                )
            ),
        )

    def _average_rating(self):
        return (
            select(func.avg(Review.rating))
            .where(
                Review.tenant_id == Product.tenant_id,
                Review.product_id == Product.id,
                Review.is_approved.is_(True),
            )
            .correlate(Product)
            .scalar_subquery()
        )

    def _units_sold(self):
        return (
            select(func.coalesce(func.sum(OrderItem.quantity), 0))
            .join(
                Order,
                and_(
                    Order.tenant_id == OrderItem.tenant_id,
                    Order.id == OrderItem.order_id,
                ),
            )
            .where(
                OrderItem.tenant_id == Product.tenant_id,
                OrderItem.product_id == Product.id,
                Order.status != OrderStatus.CANCELLED.value,
            )
            .correlate(Product)
            .scalar_subquery()
        )

    def _discovery_select(self, filters: ProductFilters, average_rating) -> Select | None:
        """The filtered, grouped statement, or None when the query can match nothing."""
        stmt = (
            select(
                Product,
                func.min(effective_price_sql()).label("min_price"),
                func.max(effective_price_sql()).label("max_price"),
                average_rating.label("rating"),
            )
            .join(
                ProductVariant,
                and_(
                    ProductVariant.tenant_id == Product.tenant_id,
                    ProductVariant.product_id == Product.id,
                ),
            )
            .where(
                Product.tenant_id == self.tenant_id,
                Product.status == CatalogueStatus.ACTIVE.value,
                ProductVariant.status == CatalogueStatus.ACTIVE.value,
            )
        )

        if filters.search:
            tokens = tokenize(filters.search)
            if not tokens:
                return None
            for token in tokens:
                stmt = stmt.where(self._token_matches(token))

        if filters.category_id:
            stmt = stmt.where(
                Product.category_id.in_(
                    category_subtree(self.tenant_id, filters.category_id)
                )
            )

        if filters.brand:
            stmt = stmt.where(func.lower(Product.brand) == filters.brand.lower())

        if filters.gender:
            stmt = stmt.where(func.lower(Product.gender) == filters.gender.lower())

        for column, value in (
            (Product.fabric, filters.fabric),
            (Product.occasion, filters.occasion),
            (Product.sleeve, filters.sleeve),
            (Product.neckline, filters.neckline),
        ):
            if value and value.strip():
                stmt = stmt.where(attribute_matches(column, value))

        matching_variant = self._has_matching_variant(filters)
        if matching_variant is not None:
            stmt = stmt.where(matching_variant)

        stmt = stmt.group_by(Product.id)

        if filters.min_rating is not None:
            stmt = stmt.having(average_rating >= filters.min_rating)

        if filters.max_rating is not None:
            stmt = stmt.having(average_rating <= filters.max_rating)

        return stmt

    def _ordered(self, stmt: Select, sort: SearchSort, units_sold) -> Select:
        """Price sorts key off the price the card shows -- the cheapest live variant."""
        from_price = func.min(effective_price_sql())

        if sort is SearchSort.PRICE_LOW:
            return stmt.order_by(from_price, Product.created_at.desc())
        if sort is SearchSort.PRICE_HIGH:
            return stmt.order_by(desc(from_price), Product.created_at.desc())
        if sort is SearchSort.NEWEST:
            return stmt.order_by(desc(Product.created_at))
        return stmt.order_by(desc(units_sold), desc(Product.created_at))

    async def discover_products(
        self, filters: ProductFilters, params: PageParams
    ) -> tuple[list[DiscoveryRow], int]:
        average_rating = self._average_rating()

        stmt = self._discovery_select(filters, average_rating)
        if stmt is None:
            return [], 0

        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )

        stmt = self._ordered(stmt, filters.sort, self._units_sold())
        stmt = stmt.offset(params.offset).limit(params.limit)

        result = await self.session.execute(stmt)
        return list(result.all()), int(total or 0)

    async def variant_attributes(
        self, product_ids: list[UUID]
    ) -> dict[UUID, list[dict]]:
        """Active variant attributes for the given products, keyed by product."""
        if not product_ids:
            return {}

        stmt = (
            select(ProductVariant)
            .options(
                selectinload(ProductVariant.option_values).selectinload(
                    ProductVariantOption.option
                )
            )
            .where(
                ProductVariant.tenant_id == self.tenant_id,
                ProductVariant.product_id.in_(product_ids),
                ProductVariant.status == CatalogueStatus.ACTIVE.value,
            )
            .order_by(ProductVariant.created_at)
        )
        result = await self.session.scalars(stmt)

        attributes: dict[UUID, list[dict]] = {pid: [] for pid in product_ids}
        for variant in result.all():
            options = {
                option_value.option.name: option_value.value
                for option_value in variant.option_values
            }
            attributes.setdefault(variant.product_id, []).append(
                {"variant_id": variant.id, "options": options}
            )
        return attributes

    async def suggestions(self, query: str) -> list[str]:
        """Product names, brands and categories matching the query, prefixes first."""
        term = escape_like(query.replace("'", ""))
        contains = f"%{term}%"

        def _clean(column):
            return func.replace(column, "'", "")

        def _matching(column, *conditions):
            return select(column.label("title")).where(
                *conditions, _clean(column).ilike(contains, escape="\\")
            )

        active_product = (
            Product.tenant_id == self.tenant_id,
            Product.status == CatalogueStatus.ACTIVE.value,
        )

        matches = union(
            _matching(Product.name, *active_product),
            _matching(Product.brand, *active_product),
            _matching(
                Category.name,
                Category.tenant_id == self.tenant_id,
                Category.status == CatalogueStatus.ACTIVE.value,
            ),
        ).subquery()

        title = matches.c.title
        starts_with = func.replace(title, "'", "").ilike(f"{term}%", escape="\\")
        stmt = (
            select(title)
            .order_by(case((starts_with, 0), else_=1), title)
            .limit(MAX_SUGGESTIONS)
        )

        result = await self.session.scalars(stmt)
        return list(result.all())

    async def record_search(self, user_id: UUID, query: str) -> None:
        """Store the phrase, or bump it if this shopper has searched it before."""
        entry = await self.find_one(
            SearchHistory.user_id == user_id, SearchHistory.query == query
        )

        if entry is None:
            await self.add(SearchHistory(user_id=user_id, query=query))
        else:
            entry.searched_at = datetime.now(timezone.utc)
            await self.session.flush()

        stale = (
            self.base_select()
            .with_only_columns(SearchHistory.id)
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.searched_at))
            .offset(MAX_HISTORY_ENTRIES)
        )
        await self.session.execute(
            delete(SearchHistory).where(SearchHistory.id.in_(stale))
        )

    async def recent_searches(self, user_id: UUID) -> list[str]:
        stmt = (
            self.base_select()
            .where(SearchHistory.user_id == user_id)
            .order_by(desc(SearchHistory.searched_at))
            .limit(MAX_HISTORY_ENTRIES)
        )
        result = await self.session.scalars(stmt)
        return [entry.query for entry in result.all()]
