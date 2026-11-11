from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.pagination import PageParams
from app.search_filter.repository import SearchFilterRepository
from app.search_filter.schemas import (
    ProductDiscoveryItem,
    ProductFilters,
    SuggestionItem,
    VariantAttributes,
)

PRICE_RANGE_INVERTED = "min_price cannot be greater than max_price"
RATING_RANGE_INVERTED = "min_rating cannot be greater than max_rating"


class SearchFilterService:
    """Storefront product discovery, plus the phrases a shopper has searched."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.repo = SearchFilterRepository(session, tenant_id)

    async def discover(
        self, filters: ProductFilters, params: PageParams
    ) -> tuple[list[ProductDiscoveryItem], int]:
        self._check_ranges(filters)

        rows, total = await self.repo.discover_products(filters, params)
        attributes = await self.repo.variant_attributes(
            [product.id for product, _, _, _ in rows]
        )

        items = [
            ProductDiscoveryItem(
                id=product.id,
                name=product.name,
                brand=product.brand,
                gender=product.gender,
                fabric=product.fabric,
                occasion=product.occasion,
                sleeve=product.sleeve,
                neckline=product.neckline,
                category_id=product.category_id,
                price=min_price,
                min_price=min_price,
                max_price=max_price,
                rating=round(rating, 2) if rating is not None else None,
                variants=[
                    VariantAttributes(
                        variant_id=variant["variant_id"],
                        options=variant["options"],
                    )
                    for variant in attributes.get(product.id, [])
                ],
            )
            for product, min_price, max_price, rating in rows
        ]

        return items, total

    async def suggestions(self, query: str) -> list[SuggestionItem]:
        if not query.strip():
            return []

        titles = await self.repo.suggestions(query.strip())
        return [SuggestionItem(title=title) for title in titles]

    async def record_search(self, user_id: UUID, query: str | None) -> None:
        """Remember a non-empty query. Best effort -- it never fails the search."""
        if not query or not query.strip():
            return

        try:
            await self.repo.record_search(user_id, query.strip())
            await self.session.commit()
        except IntegrityError:
            # Two identical searches raced for the same phrase; the other won.
            await self.session.rollback()

    async def recent_searches(self, user_id: UUID) -> list[str]:
        return await self.repo.recent_searches(user_id)

    @staticmethod
    def _check_ranges(filters: ProductFilters) -> None:
        if (
            filters.min_price is not None
            and filters.max_price is not None
            and filters.min_price > filters.max_price
        ):
            raise AppError(PRICE_RANGE_INVERTED)

        if (
            filters.min_rating is not None
            and filters.max_rating is not None
            and filters.min_rating > filters.max_rating
        ):
            raise AppError(RATING_RANGE_INVERTED)
