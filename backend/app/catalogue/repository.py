from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Select, and_, delete, desc, exists, func, or_, select, update
from sqlalchemy.orm import aliased

from app.catalogue.constants import CatalogueStatus, ProductSort
from app.catalogue.models import (
    Category,
    InventoryItem,
    Product,
    ProductImage,
    ProductOption,
    ProductRelation,
    ProductVariant,
    ProductVariantOption,
)
from app.catalogue.prices import effective_price_sql
from app.core.repository import TenantScopedRepository, escape_like
from app.orders.constants import OrderStatus
from app.orders.models import Order, OrderItem


def category_subtree(tenant_id: UUID, category_id: UUID) -> Select[tuple[UUID]]:
    """Ids of a category and every sub-category below it, at any depth.

    UNION rather than UNION ALL, so the recursion stops even if a cycle ever
    slipped into the data.
    """
    tree = (
        select(Category.id)
        .where(Category.tenant_id == tenant_id, Category.id == category_id)
        .cte("category_subtree", recursive=True)
    )
    child = aliased(Category)
    tree = tree.union(
        select(child.id).where(child.tenant_id == tenant_id, child.parent_id == tree.c.id)
    )
    return select(tree.c.id)


def attribute_matches(column, value: str):
    """Case-insensitive exact match for a free-text product attribute."""
    return func.lower(column) == value.strip().lower()


class CategoryRepository(TenantScopedRepository[Category]):
    model = Category

    def list_select(
        self,
        *,
        active_only: bool = False,
        status: CatalogueStatus | None = None,
        include_archived: bool = False,
        parent_id: UUID | None = None,
        top_level: bool = False,
    ) -> Select[tuple[Category]]:
        stmt = self.base_select()

        if active_only:
            stmt = stmt.where(Category.status == CatalogueStatus.ACTIVE.value)
        elif status is not None:
            stmt = stmt.where(Category.status == status.value)
        elif not include_archived:
            stmt = stmt.where(Category.status != CatalogueStatus.ARCHIVED.value)

        if parent_id is not None:
            stmt = stmt.where(Category.parent_id == parent_id)
        elif top_level:
            stmt = stmt.where(Category.parent_id.is_(None))

        return stmt.order_by(Category.name)

    async def has_live_children(self, category_id: UUID) -> bool:
        """Whether any sub-category under it is not archived."""
        return (
            await self.find_one(
                Category.parent_id == category_id,
                Category.status != CatalogueStatus.ARCHIVED.value,
            )
            is not None
        )

    async def is_within(self, category_id: UUID, root_id: UUID) -> bool:
        """Whether category_id is root_id itself or sits anywhere below it."""
        subtree = category_subtree(self.tenant_id, root_id).subquery()
        found = await self.session.scalar(
            select(subtree.c.id).where(subtree.c.id == category_id).limit(1)
        )
        return found is not None


class ProductRepository(TenantScopedRepository[Product]):
    model = Product

    def _live_price_subquery(self):
        """Cheapest sellable variant price for the product, used for price sorting."""
        return (
            select(func.min(effective_price_sql()))
            .where(
                ProductVariant.tenant_id == Product.tenant_id,
                ProductVariant.product_id == Product.id,
                ProductVariant.status == CatalogueStatus.ACTIVE.value,
            )
            .correlate(Product)
            .scalar_subquery()
        )

    def list_select(
        self,
        *,
        category_id: UUID | None = None,
        search: str | None = None,
        brand: str | None = None,
        fabric: str | None = None,
        occasion: str | None = None,
        sleeve: str | None = None,
        neckline: str | None = None,
        featured: bool | None = None,
        min_price: Decimal | None = None,
        max_price: Decimal | None = None,
        sort: ProductSort = ProductSort.NAME_ASC,
        active_only: bool = False,
        status: CatalogueStatus | None = None,
    ) -> Select[tuple[Product]]:
        stmt = self.base_select()

        if active_only:
            stmt = stmt.join(
                Category,
                and_(
                    Category.id == Product.category_id,
                    Category.tenant_id == Product.tenant_id,
                ),
            ).where(
                Product.status == CatalogueStatus.ACTIVE.value,
                Category.status == CatalogueStatus.ACTIVE.value,
            )
        elif status is not None:
            stmt = stmt.where(Product.status == status.value)
        else:
            stmt = stmt.where(Product.status != CatalogueStatus.ARCHIVED.value)

        if category_id is not None:
            # A category's listing includes the products of its sub-categories.
            stmt = stmt.where(
                Product.category_id.in_(category_subtree(self.tenant_id, category_id))
            )

        if search:
            pattern = f"%{escape_like(search.strip())}%"
            stmt = stmt.where(
                or_(
                    Product.name.ilike(pattern, escape="\\"),
                    Product.brand.ilike(pattern, escape="\\"),
                )
            )

        if brand:
            stmt = stmt.where(Product.brand == brand.strip())

        for column, value in (
            (Product.fabric, fabric),
            (Product.occasion, occasion),
            (Product.sleeve, sleeve),
            (Product.neckline, neckline),
        ):
            if value and value.strip():
                stmt = stmt.where(attribute_matches(column, value))

        if featured is not None:
            stmt = stmt.where(Product.is_featured.is_(featured))

        if min_price is not None or max_price is not None:
            conditions = [
                ProductVariant.tenant_id == Product.tenant_id,
                ProductVariant.product_id == Product.id,
                ProductVariant.status == CatalogueStatus.ACTIVE.value,
            ]
            price = effective_price_sql()
            if min_price is not None:
                conditions.append(price >= min_price)
            if max_price is not None:
                conditions.append(price <= max_price)
            stmt = stmt.where(exists().where(and_(*conditions)))

        return stmt.order_by(*self._order_by(sort))

    def _order_by(self, sort: ProductSort):
        price = self._live_price_subquery()
        clauses = {
            ProductSort.NEWEST: (Product.created_at.desc(), Product.id),
            ProductSort.NAME_ASC: (Product.name.asc(), Product.id),
            ProductSort.NAME_DESC: (Product.name.desc(), Product.id),
            ProductSort.PRICE_LOW: (price.asc().nulls_last(), Product.id),
            ProductSort.PRICE_HIGH: (price.desc().nulls_last(), Product.id),
        }
        return clauses[sort]

    async def attribute_values(
        self,
        column,
        *,
        active_only: bool,
        category_id: UUID | None = None,
    ) -> list[tuple[str, int]]:
        """Distinct non-empty values of one product attribute, with product counts."""
        stmt = (
            select(column, func.count(Product.id))
            .where(Product.tenant_id == self.tenant_id, column.isnot(None))
            .group_by(column)
            .order_by(column)
        )
        if active_only:
            stmt = stmt.join(
                Category,
                and_(
                    Category.id == Product.category_id,
                    Category.tenant_id == Product.tenant_id,
                ),
            ).where(
                Product.status == CatalogueStatus.ACTIVE.value,
                Category.status == CatalogueStatus.ACTIVE.value,
            )
        else:
            stmt = stmt.where(Product.status != CatalogueStatus.ARCHIVED.value)

        if category_id is not None:
            stmt = stmt.where(
                Product.category_id.in_(category_subtree(self.tenant_id, category_id))
            )

        return [(value, count) for value, count in (await self.session.execute(stmt)).all()]

    async def live_products(self, product_ids: list[UUID]) -> list[Product]:
        """The ACTIVE ones among these ids (in an ACTIVE category), in the given order."""
        if not product_ids:
            return []
        stmt = (
            self.base_select()
            .join(
                Category,
                and_(
                    Category.id == Product.category_id,
                    Category.tenant_id == Product.tenant_id,
                ),
            )
            .where(
                Product.id.in_(product_ids),
                Product.status == CatalogueStatus.ACTIVE.value,
                Category.status == CatalogueStatus.ACTIVE.value,
            )
        )
        found = {product.id: product for product in (await self.session.scalars(stmt)).all()}
        return [found[pid] for pid in product_ids if pid in found]

    async def live_in_category(
        self, category_id: UUID, *, exclude: list[UUID], limit: int
    ) -> list[Product]:
        """Newest ACTIVE products from the same category, a fallback for related lists."""
        if limit <= 0:
            return []
        stmt = (
            self.base_select()
            .where(
                Product.category_id == category_id,
                Product.status == CatalogueStatus.ACTIVE.value,
                Product.id.notin_(exclude),
            )
            .order_by(Product.created_at.desc(), Product.id)
            .limit(limit)
        )
        return list((await self.session.scalars(stmt)).all())

    async def bought_together(self, product_id: UUID, *, limit: int) -> list[UUID]:
        """Products most often in the same (non-cancelled) orders as this one."""
        mine = aliased(OrderItem)
        other = aliased(OrderItem)
        stmt = (
            select(other.product_id, func.count(func.distinct(other.order_id)).label("n"))
            .join(
                mine,
                and_(mine.tenant_id == other.tenant_id, mine.order_id == other.order_id),
            )
            .join(
                Order,
                and_(Order.tenant_id == other.tenant_id, Order.id == other.order_id),
            )
            .where(
                other.tenant_id == self.tenant_id,
                mine.product_id == product_id,
                other.product_id != product_id,
                Order.status != OrderStatus.CANCELLED.value,
            )
            .group_by(other.product_id)
            .order_by(desc("n"), other.product_id)
            .limit(limit)
        )
        return [row[0] for row in (await self.session.execute(stmt)).all()]

    async def has_products_in_category(
        self, category_id: UUID, *, include_archived: bool = False
    ) -> bool:
        """Whether the category still holds products, archived ones excluded."""
        conditions = [Product.category_id == category_id]
        if not include_archived:
            conditions.append(Product.status != CatalogueStatus.ARCHIVED.value)

        return await self.find_one(*conditions) is not None

    async def lock(self, product_id: UUID) -> UUID | None:
        """Take a row lock on the product, serialising mutations to its image set."""
        return await self.session.scalar(
            select(Product.id)
            .where(Product.tenant_id == self.tenant_id, Product.id == product_id)
            .with_for_update()
        )


class ProductRelationRepository(TenantScopedRepository[ProductRelation]):
    model = ProductRelation

    async def for_product(self, product_id: UUID) -> list[ProductRelation]:
        stmt = (
            self.base_select()
            .where(ProductRelation.product_id == product_id)
            .order_by(ProductRelation.position, ProductRelation.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def replace(self, product_id: UUID, related_ids: list[UUID]) -> None:
        await self.session.execute(
            delete(ProductRelation).where(
                ProductRelation.tenant_id == self.tenant_id,
                ProductRelation.product_id == product_id,
            )
        )
        for position, related_id in enumerate(related_ids):
            self.session.add(
                ProductRelation(
                    tenant_id=self.tenant_id,
                    product_id=product_id,
                    related_product_id=related_id,
                    position=position,
                )
            )
        await self.session.flush()


class VariantRepository(TenantScopedRepository[ProductVariant]):
    model = ProductVariant

    def list_select(
        self, product_id: UUID, *, active_only: bool = False
    ) -> Select[tuple[ProductVariant]]:
        stmt = self.base_select().where(ProductVariant.product_id == product_id)

        if active_only:
            stmt = stmt.where(ProductVariant.status == CatalogueStatus.ACTIVE.value)

        return stmt.order_by(ProductVariant.sku)

    async def get_by_sku(self, sku: str) -> ProductVariant | None:
        return await self.find_one(ProductVariant.sku == sku)


class ProductOptionRepository(TenantScopedRepository[ProductOption]):
    model = ProductOption

    def list_select(self, product_id: UUID) -> Select[tuple[ProductOption]]:
        return (
            self.base_select()
            .where(ProductOption.product_id == product_id)
            .order_by(ProductOption.position, ProductOption.name)
        )

class VariantOptionRepository(TenantScopedRepository[ProductVariantOption]):
    model = ProductVariantOption

    async def clear_for_variant(self, variant_id: UUID) -> None:
        await self.session.execute(
            ProductVariantOption.__table__.delete().where(
                ProductVariantOption.tenant_id == self.tenant_id,
                ProductVariantOption.variant_id == variant_id,
            )
        )
        await self.session.flush()


class ProductImageRepository(TenantScopedRepository[ProductImage]):
    model = ProductImage

    def list_select(self, product_id: UUID) -> Select[tuple[ProductImage]]:
        return (
            self.base_select()
            .where(ProductImage.product_id == product_id)
            .order_by(ProductImage.sort_order, ProductImage.created_at)
        )

    async def count_for_product(self, product_id: UUID) -> int:
        total = await self.session.scalar(
            select(func.count())
            .select_from(ProductImage)
            .where(
                ProductImage.tenant_id == self.tenant_id,
                ProductImage.product_id == product_id,
            )
        )
        return int(total or 0)

    async def primary_for(self, product_ids: list[UUID]) -> dict[UUID, ProductImage]:
        """Primary image per product, for a whole list of products in one query."""
        if not product_ids:
            return {}
        rows = await self.session.scalars(
            select(ProductImage).where(
                ProductImage.tenant_id == self.tenant_id,
                ProductImage.product_id.in_(product_ids),
                ProductImage.is_primary.is_(True),
            )
        )
        return {image.product_id: image for image in rows.all()}

    async def clear_primary(
        self, product_id: UUID, *, exclude_id: UUID | None = None
    ) -> None:
        """Demote the product's current primary image in a single UPDATE."""
        conditions = [
            ProductImage.tenant_id == self.tenant_id,
            ProductImage.product_id == product_id,
            ProductImage.is_primary.is_(True),
        ]
        if exclude_id is not None:
            conditions.append(ProductImage.id != exclude_id)

        await self.session.execute(
            update(ProductImage).where(*conditions).values(is_primary=False)
        )
        await self.session.flush()


class InventoryRepository(TenantScopedRepository[InventoryItem]):
    """Stock changes as conditional UPDATEs; a rowcount of 0 means it was refused."""

    model = InventoryItem

    async def get_for_variant(self, variant_id: UUID) -> InventoryItem | None:
        return await self.find_one(InventoryItem.variant_id == variant_id)

    async def _apply(self, variant_id: UUID, *conditions, **values) -> bool:
        result = await self.session.execute(
            update(InventoryItem)
            .where(
                InventoryItem.tenant_id == self.tenant_id,
                InventoryItem.variant_id == variant_id,
                *conditions,
            )
            .values(**values)
        )
        await self.session.flush()
        return (result.rowcount or 0) == 1

    async def set_available(self, variant_id: UUID, quantity: int) -> bool:
        return await self._apply(
            variant_id,
            InventoryItem.reserved_quantity <= quantity,
            available_quantity=quantity,
        )

    async def adjust_available(self, variant_id: UUID, delta: int) -> bool:
        return await self._apply(
            variant_id,
            InventoryItem.available_quantity + delta >= InventoryItem.reserved_quantity,
            InventoryItem.available_quantity + delta >= 0,
            available_quantity=InventoryItem.available_quantity + delta,
        )

    async def reserve(self, variant_id: UUID, quantity: int) -> bool:
        return await self._apply(
            variant_id,
            InventoryItem.available_quantity - InventoryItem.reserved_quantity >= quantity,
            reserved_quantity=InventoryItem.reserved_quantity + quantity,
        )

    async def release(self, variant_id: UUID, quantity: int) -> bool:
        return await self._apply(
            variant_id,
            InventoryItem.reserved_quantity >= quantity,
            reserved_quantity=InventoryItem.reserved_quantity - quantity,
        )

    async def fulfil(self, variant_id: UUID, quantity: int) -> bool:
        """Ship reserved stock: it leaves the shelf and the reservation ends."""
        return await self._apply(
            variant_id,
            InventoryItem.reserved_quantity >= quantity,
            InventoryItem.available_quantity >= quantity,
            available_quantity=InventoryItem.available_quantity - quantity,
            reserved_quantity=InventoryItem.reserved_quantity - quantity,
        )

    async def set_threshold(self, variant_id: UUID, threshold: int) -> bool:
        return await self._apply(variant_id, low_stock_threshold=threshold)
