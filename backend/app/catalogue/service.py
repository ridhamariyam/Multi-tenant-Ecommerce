from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalogue.constants import (
    MAX_OPTIONS_PER_PRODUCT,
    MAX_SLUG_LENGTH,
    MIN_PRODUCT_IMAGES,
    CatalogueStatus,
    InventoryReason,
    ProductAttribute,
)
from app.catalogue.models import (
    Category,
    InventoryItem,
    InventoryMovement,
    Product,
    ProductAttributeValue,
    ProductImage,
    ProductOption,
    ProductVariant,
    ProductVariantOption,
)
from app.catalogue.repository import (
    CategoryRepository,
    InventoryRepository,
    ProductImageRepository,
    ProductOptionRepository,
    ProductRelationRepository,
    ProductRepository,
    VariantOptionRepository,
    VariantRepository,
)
from app.catalogue.schemas import (
    AttributeValueCreate,
    AttributeValueRead,
    CategoryCreate,
    CategoryQuery,
    CategoryUpdate,
    ImageReorderPayload,
    ProductCreate,
    ProductImageCreate,
    ProductImageUpdate,
    ProductQuery,
    ProductUpdate,
    VariantCreate,
    VariantOptionValue,
    VariantUpdate,
)
from app.core.database import conflict_on_integrity_error
from app.core.error_codes import CommonErrorCode, InventoryErrorCode, ProductErrorCode
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.pagination import PageParams
from app.core.slugs import slugify, with_suffix

PRODUCT_NOT_FOUND = "Product not found"
CATEGORY_NOT_FOUND = "Category not found"
VARIANT_NOT_FOUND = "Variant not found"
IMAGE_NOT_FOUND = "Product image not found"
LAST_IMAGE = "A product must have at least one image"
PARENT_NOT_FOUND = "Parent category not found"
SELLABLE_VARIANT_NOT_FOUND = "Product variant not found"
VARIANT_UNAVAILABLE = "Product variant is not available"
PRODUCT_UNAVAILABLE = "Product is not available"
ATTRIBUTE_VALUE_NOT_FOUND = "Attribute value not found"
DUPLICATE_ATTRIBUTE_VALUE = "This value is already in the list"


def _check_sale(price, sale_price, starts_at, ends_at) -> None:
    """A scheduled sale must undercut the regular price and run forwards in time."""
    if sale_price is None:
        if starts_at is not None or ends_at is not None:
            raise ValidationError("A sale window needs a sale price")
        return
    if price is not None and sale_price >= price:
        raise ValidationError("The sale price must be lower than the regular price")
    if starts_at is not None and ends_at is not None and starts_at >= ends_at:
        raise ValidationError("The sale must start before it ends")


class CategoryService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.categories = CategoryRepository(session, tenant_id)
        self.products = ProductRepository(session, tenant_id)

    async def _require_parent(self, parent_id: UUID) -> Category:
        """A sub-category's parent must exist in this tenant and not be archived."""
        parent = await self.categories.get(parent_id)
        if parent is None:
            raise NotFoundError(PARENT_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)
        if parent.status == CatalogueStatus.ARCHIVED.value:
            raise ConflictError(
                "Parent category is archived and cannot take sub-categories",
                error_code=ProductErrorCode.CATEGORY_ARCHIVED,
            )
        return parent

    async def create(self, data: CategoryCreate) -> Category:
        if data.parent_id is not None:
            await self._require_parent(data.parent_id)

        category = Category(
            parent_id=data.parent_id,
            name=data.name,
            description=data.description,
            status=data.status.value,
            hsn_code=data.hsn_code,
            gst_rate=data.gst_rate,
        )
        async with conflict_on_integrity_error(self.session, "Unable to create category"):
            await self.categories.add(category)
            await self.session.commit()

        return category

    async def get(self, category_id: UUID) -> Category:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)
        return category

    async def get_public(self, category_id: UUID) -> Category:
        category = await self.get(category_id)
        if category.status != CatalogueStatus.ACTIVE.value:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)
        return category

    async def list(
        self, query: CategoryQuery, *, active_only: bool = False
    ) -> tuple[list[Category], int]:
        """One page of categories matching the query's filters."""
        filters = query.model_dump(exclude={"page", "page_size"})
        stmt = self.categories.list_select(**filters, active_only=active_only)
        rows, total = await self.categories.paginate(stmt, query)
        return list(rows), total

    async def update(self, category_id: UUID, data: CategoryUpdate) -> Category:
        category = await self.get(category_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("status") is not None:
            changes["status"] = changes["status"].value

        new_parent = changes.get("parent_id")
        if new_parent is not None:
            await self._require_parent(new_parent)
            # Moving a category under itself or one of its own descendants
            # would turn the tree into a loop.
            if await self.categories.is_within(new_parent, category.id):
                raise ConflictError(
                    "A category cannot be moved under itself or one of its sub-categories"
                )

        for field, value in changes.items():
            setattr(category, field, value)

        async with conflict_on_integrity_error(self.session, "Unable to update category"):
            await self.session.commit()

        return category

    async def delete(self, category_id: UUID) -> None:
        """Archive the category rather than deleting it; live products block it."""
        category = await self.get(category_id)

        if category.status == CatalogueStatus.ARCHIVED.value:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)

        if await self.products.has_products_in_category(category.id):
            raise ConflictError(
                "Category still has active products and cannot be deleted",
                error_code=ProductErrorCode.CATEGORY_IN_USE,
            )

        if await self.categories.has_live_children(category.id):
            raise ConflictError(
                "Category still has sub-categories and cannot be deleted",
                error_code=ProductErrorCode.CATEGORY_IN_USE,
            )

        category.status = CatalogueStatus.ARCHIVED.value
        await self.session.commit()



class ProductService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.products = ProductRepository(session, tenant_id)
        self.categories = CategoryRepository(session, tenant_id)
        self.images = ProductImageRepository(session, tenant_id)
        self.relations = ProductRelationRepository(session, tenant_id)

    async def _require_category(self, category_id: UUID) -> Category:
        category = await self.categories.get(category_id)
        if category is None:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)
        if category.status == CatalogueStatus.ARCHIVED.value:
            raise ConflictError(
                "Category is archived and cannot take products",
                error_code=ProductErrorCode.CATEGORY_ARCHIVED,
            )
        return category

    async def create(self, data: ProductCreate) -> Product:
        """Create a product together with its images in one transaction."""
        await self._require_category(data.category_id)
        slug = (
            await self._require_free_slug(data.slug)
            if data.slug
            else await self._unique_slug(data.name)
        )

        product = Product(
            category_id=data.category_id,
            name=data.name,
            slug=slug,
            short_description=data.short_description,
            description=data.description,
            brand=data.brand,
            status=data.status.value,
            gender=data.gender.value if data.gender is not None else None,
            fabric=data.fabric,
            occasion=data.occasion,
            sleeve=data.sleeve,
            neckline=data.neckline,
            fabric_details=data.fabric_details,
            washing_instructions=data.washing_instructions,
            country_of_origin=data.country_of_origin,
            size_chart=data.size_chart.to_storage() if data.size_chart else None,
            hsn_code=data.hsn_code,
            gst_rate=data.gst_rate,
            is_featured=data.is_featured,
            seo_title=data.seo_title,
            seo_description=data.seo_description,
        )

        async with conflict_on_integrity_error(self.session, "Unable to create product"):
            await self.products.add(product)

            has_primary = any(image.is_primary for image in data.images)
            for position, image in enumerate(data.images):
                await self.images.add(
                    ProductImage(
                        product_id=product.id,
                        url=image.url,
                        alt_text=image.alt_text,
                        sort_order=image.sort_order,
                        is_primary=image.is_primary
                        or (not has_primary and position == 0),
                    )
                )

            await self.session.commit()

        return await self.get(product.id)

    async def get(self, product_id: UUID) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)
        return product

    async def _slug_taken(self, slug: str, exclude: UUID | None = None) -> bool:
        stmt = select(Product.id).where(Product.tenant_id == self.tenant_id, Product.slug == slug)
        if exclude is not None:
            stmt = stmt.where(Product.id != exclude)
        return await self.session.scalar(stmt) is not None

    async def _require_free_slug(self, slug: str, exclude: UUID | None = None) -> str:
        if await self._slug_taken(slug, exclude):
            raise ConflictError(
                f"The product URL '{slug}' is already used", error_code=CommonErrorCode.SLUG_TAKEN
            )
        return slug

    async def _unique_slug(self, name: str) -> str:
        """A slug from the name; a second 'Cotton Kurta' becomes cotton-kurta-2."""
        base = slugify(name, MAX_SLUG_LENGTH, fallback="product")
        slug, n = base, 1
        while await self._slug_taken(slug):
            n += 1
            slug = with_suffix(base, n, MAX_SLUG_LENGTH)
        return slug

    async def get_public_by_slug(self, slug: str) -> Product:
        product_id = await self.session.scalar(
            select(Product.id).where(Product.tenant_id == self.tenant_id, Product.slug == slug)
        )
        if product_id is None:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)
        return await self.get_public(product_id)

    async def get_public(self, product_id: UUID) -> Product:
        """Fetch a product only when it is ACTIVE and its category is too."""
        product = await self.get(product_id)

        if product.status != CatalogueStatus.ACTIVE.value:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)

        category = await self.categories.get(product.category_id)
        if category is None or category.status != CatalogueStatus.ACTIVE.value:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)

        return product

    async def list(
        self, query: ProductQuery, *, active_only: bool = False
    ) -> tuple[list[Product], int]:
        """One page of products matching the query's filters, in its sort order."""
        if query.category_id is not None and await self.categories.get(query.category_id) is None:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)

        filters = query.model_dump(exclude={"page", "page_size"})
        stmt = self.products.list_select(**filters, active_only=active_only)
        rows, total = await self.products.paginate(stmt, query)
        return list(rows), total

    async def update(self, product_id: UUID, data: ProductUpdate) -> Product:
        product = await self.get(product_id)
        changes = data.model_dump(exclude_unset=True)

        if changes.get("category_id") is not None:
            await self._require_category(changes["category_id"])

        if changes.get("status") is not None:
            changes["status"] = changes["status"].value

        if changes.get("gender") is not None:
            changes["gender"] = changes["gender"].value

        if "slug" in changes:
            if not changes["slug"]:
                raise ValidationError("A product URL cannot be empty")
            await self._require_free_slug(changes["slug"], exclude=product.id)

        if "size_chart" in changes:
            changes["size_chart"] = (
                data.size_chart.to_storage() if data.size_chart is not None else None
            )

        for field, value in changes.items():
            setattr(product, field, value)

        async with conflict_on_integrity_error(self.session, "Unable to update product"):
            await self.session.commit()

        return await self.get(product.id)

    async def related(self, product_id: UUID) -> list[tuple[Product, int]]:
        """The hand-picked related products, with their display positions."""
        await self.get(product_id)
        related: list[tuple[Product, int]] = []
        for link in await self.relations.for_product(product_id):
            other = await self.products.get(link.related_product_id)
            if other is not None:
                related.append((other, link.position))
        return related

    async def set_related(
        self, product_id: UUID, related_ids: list[UUID]
    ) -> list[tuple[Product, int]]:
        """Replace the related list wholesale; order is display order."""
        await self.get(product_id)

        if product_id in related_ids:
            raise ValidationError("A product cannot be related to itself")
        for related_id in related_ids:
            if await self.products.get(related_id) is None:
                raise NotFoundError(
                    f"Related product {related_id} not found",
                    error_code=ProductErrorCode.PRODUCT_NOT_FOUND,
                )

        await self.relations.replace(product_id, related_ids)
        await self.session.commit()

        return await self.related(product_id)

    async def related_for_storefront(
        self, product_id: UUID, *, limit: int
    ) -> tuple[list[Product], list[Product]]:
        """("you may also like", "customers also bought") for a public product.

        The first list is the hand-picked one, topped up with the newest
        products of the same category; the second comes from real orders.
        """
        product = await self.get_public(product_id)

        links = await self.relations.for_product(product_id)
        picked_ids = [link.related_product_id for link in links]
        liked = (await self.products.live_products(picked_ids))[:limit]
        if len(liked) < limit:
            liked += await self.products.live_in_category(
                product.category_id,
                exclude=[product_id, *(p.id for p in liked)],
                limit=limit - len(liked),
            )

        bought_ids = await self.products.bought_together(product_id, limit=limit * 2)
        bought = (await self.products.live_products(bought_ids))[:limit]
        return liked, bought

    async def filter_options(
        self, *, active_only: bool, category_id: UUID | None = None
    ) -> dict[str, list[tuple[str, int]]]:
        """Every fabric/occasion/sleeve/neckline value in use, with how many products have it."""
        if category_id is not None and await self.categories.get(category_id) is None:
            raise NotFoundError(CATEGORY_NOT_FOUND, error_code=ProductErrorCode.CATEGORY_NOT_FOUND)

        return {
            name: await self.products.attribute_values(
                column, active_only=active_only, category_id=category_id
            )
            for name, column in (
                ("fabric", Product.fabric),
                ("occasion", Product.occasion),
                ("sleeve", Product.sleeve),
                ("neckline", Product.neckline),
            )
        }

    async def delete(self, product_id: UUID) -> None:
        """Archive the product and its variants in one transaction."""
        product = await self.get(product_id)

        if product.status == CatalogueStatus.ARCHIVED.value:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)

        product.status = CatalogueStatus.ARCHIVED.value

        await self.session.execute(
            update(ProductVariant)
            .where(
                ProductVariant.tenant_id == self.tenant_id,
                ProductVariant.product_id == product_id,
                ProductVariant.status != CatalogueStatus.ARCHIVED.value,
            )
            .values(status=CatalogueStatus.ARCHIVED.value)
        )

        await self.session.commit()



class VariantService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.variants = VariantRepository(session, tenant_id)
        self.products = ProductRepository(session, tenant_id)
        self.options = ProductOptionRepository(session, tenant_id)
        self.variant_options = VariantOptionRepository(session, tenant_id)
        self.inventory = InventoryRepository(session, tenant_id)

    async def _require_product(self, product_id: UUID) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)
        return product

    async def _sync_options(
        self, product_id: UUID, variant_id: UUID, options: list[VariantOptionValue]
    ) -> None:
        """Attach option values to a variant, reusing the product's option names."""
        existing = list(
            (await self.session.scalars(self.options.list_select(product_id))).all()
        )
        by_name = {option.name.lower(): option for option in existing}

        for entry in options:
            option = by_name.get(entry.name.lower())
            if option is None:
                if len(by_name) >= MAX_OPTIONS_PER_PRODUCT:
                    raise ConflictError(
                        f"A product may have at most {MAX_OPTIONS_PER_PRODUCT} options"
                    )
                option = await self.options.add(
                    ProductOption(
                        product_id=product_id,
                        name=entry.name,
                        position=len(by_name),
                    )
                )
                by_name[entry.name.lower()] = option

            await self.variant_options.add(
                ProductVariantOption(
                    variant_id=variant_id,
                    option_id=option.id,
                    value=entry.value,
                )
            )

    async def create(self, product_id: UUID, data: VariantCreate) -> ProductVariant:
        product = await self._require_product(product_id)

        if product.status == CatalogueStatus.ARCHIVED.value:
            raise ConflictError(
                "Cannot add a variant to an archived product",
                error_code=ProductErrorCode.PRODUCT_ARCHIVED,
            )

        sku = data.sku.strip().upper()
        if await self.variants.get_by_sku(sku) is not None:
            raise ConflictError(
                "A variant with this SKU already exists",
                error_code=ProductErrorCode.SKU_TAKEN,
            )

        _check_sale(data.price, data.sale_price, data.sale_starts_at, data.sale_ends_at)

        variant = ProductVariant(
            product_id=product_id,
            sku=sku,
            name=data.name,
            price=data.price,
            status=data.status.value,
            sale_price=data.sale_price,
            sale_starts_at=data.sale_starts_at,
            sale_ends_at=data.sale_ends_at,
        )

        async with conflict_on_integrity_error(
            self.session,
            "A variant with this SKU already exists",
            error_code=ProductErrorCode.SKU_TAKEN,
        ):
            await self.variants.add(variant)
            await self._sync_options(product_id, variant.id, data.options)

            await self.inventory.add(
                InventoryItem(
                    variant_id=variant.id,
                    available_quantity=data.initial_quantity,
                    reserved_quantity=0,
                    low_stock_threshold=data.low_stock_threshold,
                )
            )
            if data.initial_quantity:
                self.session.add(
                    InventoryMovement(
                        tenant_id=self.tenant_id,
                        variant_id=variant.id,
                        delta=data.initial_quantity,
                        reason=InventoryReason.INITIAL.value,
                    )
                )

            await self.session.commit()

        return await self.get(variant.id)

    async def get(self, variant_id: UUID) -> ProductVariant:
        variant = await self.variants.get(variant_id)
        if variant is None:
            raise NotFoundError(VARIANT_NOT_FOUND, error_code=ProductErrorCode.VARIANT_NOT_FOUND)
        return variant

    async def list_for_product(
        self, product_id: UUID, params: PageParams, *, active_only: bool = False
    ) -> tuple[list[ProductVariant], int]:
        await self._require_product(product_id)
        stmt = self.variants.list_select(product_id, active_only=active_only)
        rows, total = await self.variants.paginate(stmt, params)
        return list(rows), total

    async def update(self, variant_id: UUID, data: VariantUpdate) -> ProductVariant:
        variant = await self.get(variant_id)
        changes = data.model_dump(exclude_unset=True)
        options = changes.pop("options", None)

        if changes.get("sku") is not None:
            sku = changes["sku"].strip().upper()
            existing = await self.variants.get_by_sku(sku)
            if existing is not None and existing.id != variant.id:
                raise ConflictError(
                    "A variant with this SKU already exists",
                    error_code=ProductErrorCode.SKU_TAKEN,
                )
            changes["sku"] = sku

        if changes.get("status") is not None:
            changes["status"] = changes["status"].value

        if "sale_price" in changes and changes["sale_price"] is None:
            # Ending a sale early clears its window too.
            changes.setdefault("sale_starts_at", None)
            changes.setdefault("sale_ends_at", None)

        _check_sale(
            changes.get("price", variant.price),
            changes.get("sale_price", variant.sale_price),
            changes.get("sale_starts_at", variant.sale_starts_at),
            changes.get("sale_ends_at", variant.sale_ends_at),
        )

        for field, value in changes.items():
            setattr(variant, field, value)

        async with conflict_on_integrity_error(
            self.session,
            "A variant with this SKU already exists",
            error_code=ProductErrorCode.SKU_TAKEN,
        ):
            if options is not None:
                await self.variant_options.clear_for_variant(variant.id)
                await self._sync_options(
                    variant.product_id,
                    variant.id,
                    [VariantOptionValue(**entry) for entry in options],
                )
            await self.session.commit()

        return await self.get(variant.id)

    async def delete(self, variant_id: UUID) -> None:
        """Archive the variant; carts and orders will reference it."""
        variant = await self.get(variant_id)

        if variant.status == CatalogueStatus.ARCHIVED.value:
            raise NotFoundError(VARIANT_NOT_FOUND, error_code=ProductErrorCode.VARIANT_NOT_FOUND)

        variant.status = CatalogueStatus.ARCHIVED.value
        await self.session.commit()



class ProductImageService:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.images = ProductImageRepository(session, tenant_id)
        self.products = ProductRepository(session, tenant_id)

    async def _require_product(self, product_id: UUID) -> Product:
        product = await self.products.get(product_id)
        if product is None:
            raise NotFoundError(PRODUCT_NOT_FOUND, error_code=ProductErrorCode.PRODUCT_NOT_FOUND)
        return product

    async def _require_image(self, image_id: UUID) -> ProductImage:
        image = await self.images.get(image_id)
        if image is None:
            raise NotFoundError(IMAGE_NOT_FOUND)
        return image

    async def list_for_product(self, product_id: UUID) -> list[ProductImage]:
        await self._require_product(product_id)
        result = await self.session.scalars(self.images.list_select(product_id))
        return list(result.all())

    async def add(self, product_id: UUID, data: ProductImageCreate) -> ProductImage:
        return await self._attach(
            product_id,
            url=data.url,
            alt_text=data.alt_text,
            sort_order=data.sort_order,
            is_primary=data.is_primary,
        )

    async def ensure_product(self, product_id: UUID) -> None:
        """404 unless the product exists in this brand."""
        await self._require_product(product_id)

    async def add_uploaded(
        self,
        product_id: UUID,
        *,
        url: str,
        alt_text: str | None,
        sort_order: int,
        is_primary: bool,
    ) -> ProductImage:
        """For a URL this service produced. Client-supplied URLs go through add()."""
        return await self._attach(
            product_id,
            url=url,
            alt_text=alt_text,
            sort_order=sort_order,
            is_primary=is_primary,
        )

    async def _attach(
        self,
        product_id: UUID,
        *,
        url: str,
        alt_text: str | None,
        sort_order: int,
        is_primary: bool,
    ) -> ProductImage:
        product = await self._require_product(product_id)

        if product.status == CatalogueStatus.ARCHIVED.value:
            raise ConflictError(
                "Cannot add an image to an archived product",
                error_code=ProductErrorCode.PRODUCT_ARCHIVED,
            )

        async with conflict_on_integrity_error(self.session, "Unable to add product image"):
            if is_primary:
                await self.images.clear_primary(product_id)

            image = await self.images.add(
                ProductImage(
                    product_id=product_id,
                    url=url,
                    alt_text=alt_text,
                    sort_order=sort_order,
                    is_primary=is_primary,
                )
            )
            await self.session.commit()

        return image

    async def update(self, image_id: UUID, data: ProductImageUpdate) -> ProductImage:
        image = await self._require_image(image_id)
        changes = data.model_dump(exclude_unset=True)

        async with conflict_on_integrity_error(
            self.session,
            "Another image was set as primary, please retry",
        ):
            if changes.get("is_primary") is True:
                await self.images.clear_primary(image.product_id, exclude_id=image.id)

            for field, value in changes.items():
                setattr(image, field, value)

            await self.session.commit()

        return image

    async def set_primary(self, image_id: UUID) -> ProductImage:
        image = await self._require_image(image_id)

        async with conflict_on_integrity_error(
            self.session,
            "Another image was set as primary, please retry",
        ):
            await self.images.clear_primary(image.product_id, exclude_id=image.id)
            image.is_primary = True
            await self.session.commit()

        return image

    async def reorder(
        self, product_id: UUID, data: ImageReorderPayload
    ) -> list[ProductImage]:
        await self._require_product(product_id)

        current = {image.id: image for image in await self.list_for_product(product_id)}
        unknown = [entry.id for entry in data.images if entry.id not in current]
        if unknown:
            raise NotFoundError(IMAGE_NOT_FOUND)

        for entry in data.images:
            current[entry.id].sort_order = entry.sort_order

        await self.session.commit()

        return await self.list_for_product(product_id)

    async def delete(self, image_id: UUID) -> None:
        """Remove an image, refusing to take a product's last one."""
        image = await self._require_image(image_id)

        await self.products.lock(image.product_id)

        remaining = await self.images.count_for_product(image.product_id)
        if remaining <= MIN_PRODUCT_IMAGES:
            raise ConflictError(LAST_IMAGE)

        was_primary = image.is_primary
        product_id = image.product_id
        await self.images.delete(image)

        if was_primary:
            successor = await self.session.scalar(
                self.images.list_select(product_id).limit(1)
            )
            if successor is not None:
                successor.is_primary = True

        await self.session.commit()



class InventoryService:
    """Stock operations; `commit=False` leaves the transaction to the caller."""

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id
        self.inventory = InventoryRepository(session, tenant_id)
        self.variants = VariantRepository(session, tenant_id)

    async def _require_item(self, variant_id: UUID) -> InventoryItem:
        if await self.variants.get(variant_id) is None:
            raise NotFoundError(VARIANT_NOT_FOUND, error_code=ProductErrorCode.VARIANT_NOT_FOUND)

        item = await self.inventory.get_for_variant(variant_id)
        if item is None:
            raise NotFoundError(
                "Inventory record not found",
                error_code=InventoryErrorCode.INVENTORY_NOT_FOUND,
            )
        return item

    def _record(
        self,
        variant_id: UUID,
        delta: int,
        reason: InventoryReason,
        reference: str | None = None,
        note: str | None = None,
    ) -> None:
        self.session.add(
            InventoryMovement(
                tenant_id=self.tenant_id,
                variant_id=variant_id,
                delta=delta,
                reason=reason.value,
                reference=reference,
                note=note,
            )
        )

    async def _save(self, commit: bool) -> None:
        """Commit on our own, or leave the change to the caller's transaction."""
        if commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def get(self, variant_id: UUID) -> InventoryItem:
        return await self._require_item(variant_id)

    async def set_available(
        self, variant_id: UUID, quantity: int, note: str | None = None
    ) -> InventoryItem:
        item = await self._require_item(variant_id)
        delta = quantity - item.available_quantity

        if not await self.inventory.set_available(variant_id, quantity):
            raise ConflictError(
                "Stock cannot be set below the quantity already reserved",
                error_code=InventoryErrorCode.STOCK_BELOW_RESERVED,
            )

        self._record(variant_id, delta, InventoryReason.ADJUSTMENT, note=note)
        await self.session.commit()

        return await self._require_item(variant_id)

    async def adjust(
        self,
        variant_id: UUID,
        delta: int,
        reason: InventoryReason = InventoryReason.ADJUSTMENT,
        reference: str | None = None,
        note: str | None = None,
    ) -> InventoryItem:
        await self._require_item(variant_id)

        if not await self.inventory.adjust_available(variant_id, delta):
            raise ConflictError(
                "Stock cannot go negative or below the quantity already reserved",
                error_code=InventoryErrorCode.STOCK_BELOW_RESERVED,
            )

        self._record(variant_id, delta, reason, reference, note)
        await self.session.commit()

        return await self._require_item(variant_id)

    async def set_threshold(self, variant_id: UUID, threshold: int) -> InventoryItem:
        await self._require_item(variant_id)
        await self.inventory.set_threshold(variant_id, threshold)
        await self.session.commit()
        return await self._require_item(variant_id)

    async def reserve(
        self,
        variant_id: UUID,
        quantity: int,
        reference: str | None = None,
        *,
        commit: bool = True,
    ) -> InventoryItem:
        """Hold stock for an order that has not shipped yet."""
        await self._require_item(variant_id)

        if not await self.inventory.reserve(variant_id, quantity):
            raise ConflictError(
                "Insufficient stock", error_code=InventoryErrorCode.INSUFFICIENT_STOCK
            )

        self._record(variant_id, 0, InventoryReason.RESERVATION, reference)
        await self._save(commit)
        return await self._require_item(variant_id)

    async def restock(
        self,
        variant_id: UUID,
        quantity: int,
        reference: str | None = None,
        *,
        note: str | None = None,
        commit: bool = True,
    ) -> InventoryItem:
        """Put shipped stock back on the shelf, e.g. a parcel returned undelivered."""
        await self._require_item(variant_id)

        if not await self.inventory.adjust_available(variant_id, quantity):
            raise ConflictError("Could not restock this variant")

        self._record(variant_id, quantity, InventoryReason.RESTOCK, reference, note)
        await self._save(commit)
        return await self._require_item(variant_id)

    async def release(
        self,
        variant_id: UUID,
        quantity: int,
        reference: str | None = None,
        *,
        commit: bool = True,
    ) -> InventoryItem:
        """Give reserved stock back, e.g. when an order is cancelled."""
        await self._require_item(variant_id)

        if not await self.inventory.release(variant_id, quantity):
            raise ConflictError(
                "Cannot release more stock than is reserved",
                error_code=InventoryErrorCode.STOCK_BELOW_RESERVED,
            )

        self._record(variant_id, 0, InventoryReason.RELEASE, reference)
        await self._save(commit)
        return await self._require_item(variant_id)

    async def fulfil(
        self,
        variant_id: UUID,
        quantity: int,
        reference: str | None = None,
        *,
        commit: bool = True,
    ) -> InventoryItem:
        """Ship reserved stock: it leaves the shelf and the reservation ends."""
        await self._require_item(variant_id)

        if not await self.inventory.fulfil(variant_id, quantity):
            raise ConflictError(
                "Cannot fulfil more stock than is reserved",
                error_code=InventoryErrorCode.STOCK_BELOW_RESERVED,
            )

        self._record(variant_id, -quantity, InventoryReason.FULFILLMENT, reference)
        await self._save(commit)
        return await self._require_item(variant_id)

    async def movements(
        self, variant_id: UUID, params: PageParams
    ) -> tuple[list[InventoryMovement], int]:
        await self._require_item(variant_id)

        stmt = (
            select(InventoryMovement)
            .where(
                InventoryMovement.tenant_id == self.tenant_id,
                InventoryMovement.variant_id == variant_id,
            )
            .order_by(InventoryMovement.created_at.desc())
        )
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        )
        rows = await self.session.scalars(
            stmt.offset(params.offset).limit(params.limit)
        )
        return list(rows.all()), int(total or 0)


class AttributeService:
    """Managed value lists for fabric, occasion, sleeve and neckline.

    The product editor offers the active values; products keep storing plain text,
    so older free-text values stay valid. A value can only be renamed while no
    product uses it (renaming would silently change those products' filters).
    """

    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self.session = session
        self.tenant_id = tenant_id

    def _column(self, attribute: str):
        return getattr(Product, ProductAttribute(attribute).value)

    async def _usage(self, attribute: str, value: str) -> int:
        column = self._column(attribute)
        return int(
            await self.session.scalar(
                select(func.count(Product.id)).where(
                    Product.tenant_id == self.tenant_id, func.lower(column) == value.lower()
                )
            )
            or 0
        )

    async def read(self, item: ProductAttributeValue) -> AttributeValueRead:
        return AttributeValueRead(
            id=item.id,
            attribute=item.attribute,
            value=item.value,
            is_active=item.is_active,
            position=item.position,
            product_count=await self._usage(item.attribute, item.value),
        )

    async def list(
        self, attribute: ProductAttribute | None, active_only: bool
    ) -> list[ProductAttributeValue]:
        stmt = select(ProductAttributeValue).where(
            ProductAttributeValue.tenant_id == self.tenant_id
        )
        if attribute is not None:
            stmt = stmt.where(ProductAttributeValue.attribute == attribute.value)
        if active_only:
            stmt = stmt.where(ProductAttributeValue.is_active.is_(True))
        rows = await self.session.scalars(
            stmt.order_by(
                ProductAttributeValue.attribute,
                ProductAttributeValue.position,
                func.lower(ProductAttributeValue.value),
            )
        )
        return list(rows.all())

    async def get(self, value_id: UUID) -> ProductAttributeValue:
        item = await self.session.scalar(
            select(ProductAttributeValue).where(
                ProductAttributeValue.tenant_id == self.tenant_id,
                ProductAttributeValue.id == value_id,
            )
        )
        if item is None:
            raise NotFoundError(ATTRIBUTE_VALUE_NOT_FOUND)
        return item

    async def create(self, data: AttributeValueCreate) -> ProductAttributeValue:
        top = await self.session.scalar(
            select(func.max(ProductAttributeValue.position)).where(
                ProductAttributeValue.tenant_id == self.tenant_id,
                ProductAttributeValue.attribute == data.attribute.value,
            )
        )
        item = ProductAttributeValue(
            tenant_id=self.tenant_id,
            attribute=data.attribute.value,
            value=data.value,
            is_active=data.is_active,
            position=0 if top is None else top + 1,
        )
        self.session.add(item)
        await self._commit()
        await self.session.refresh(item)
        return item

    async def update(self, value_id: UUID, changes: dict) -> ProductAttributeValue:
        item = await self.get(value_id)
        new_value = changes.get("value")
        if new_value is not None and new_value != item.value:
            in_use = await self._usage(item.attribute, item.value)
            if in_use and new_value.lower() != item.value.lower():
                raise ConflictError(
                    f"{in_use} product(s) use '{item.value}'. Add a new value and "
                    "switch this one off instead of renaming it.",
                    error_code=ProductErrorCode.VALUE_IN_USE,
                )
        for field, value in changes.items():
            setattr(item, field, value)
        await self._commit()
        await self.session.refresh(item)
        return item

    async def _commit(self) -> None:
        async with conflict_on_integrity_error(self.session, DUPLICATE_ATTRIBUTE_VALUE):
            await self.session.commit()


async def get_sellable_variant(
    session: AsyncSession, tenant_id: UUID, variant_id: UUID
) -> ProductVariant:
    """The variant a shopper may add to a cart or wishlist: it and its product are ACTIVE."""
    variant = await VariantRepository(session, tenant_id).get(variant_id)
    if variant is None:
        raise NotFoundError(
            SELLABLE_VARIANT_NOT_FOUND, error_code=ProductErrorCode.VARIANT_NOT_FOUND
        )
    if variant.status != CatalogueStatus.ACTIVE.value:
        raise ConflictError(VARIANT_UNAVAILABLE, error_code=InventoryErrorCode.PRODUCT_UNAVAILABLE)

    product = await ProductRepository(session, tenant_id).get(variant.product_id)
    if product is None or product.status != CatalogueStatus.ACTIVE.value:
        raise ConflictError(PRODUCT_UNAVAILABLE, error_code=InventoryErrorCode.PRODUCT_UNAVAILABLE)
    return variant
