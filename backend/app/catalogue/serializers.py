"""Turn catalogue ORM rows into API payloads."""

from __future__ import annotations

from decimal import Decimal

from app.catalogue.constants import CatalogueStatus
from app.catalogue.models import Category, InventoryItem, Product, ProductVariant
from app.catalogue.prices import effective_price, is_on_sale
from app.catalogue.schemas import (
    CategoryStorefrontRead,
    FilterOptionsRead,
    FilterValueCount,
    InventoryStatus,
    ProductImageStorefrontRead,
    ProductStorefrontRead,
    ProductSummaryStorefrontRead,
    StorefrontOption,
    VariantRead,
    VariantStorefrontRead,
    render_size_chart,
)


def sellable_quantity(item: InventoryItem | None) -> int:
    """Stock a customer can actually buy: on hand minus already promised."""
    if item is None:
        return 0
    return max(item.available_quantity - item.reserved_quantity, 0)


def inventory_status(item: InventoryItem) -> InventoryStatus:
    sellable = sellable_quantity(item)
    return InventoryStatus(
        variant_id=item.variant_id,
        available_quantity=item.available_quantity,
        reserved_quantity=item.reserved_quantity,
        low_stock_threshold=item.low_stock_threshold,
        sellable_quantity=sellable,
        is_low_stock=sellable <= item.low_stock_threshold,
    )


def variant_options(variant: ProductVariant) -> dict[str, str]:
    """{"Color": "Black", "Size": "M"} for one variant."""
    return {entry.option.name: entry.value for entry in variant.option_values}


def admin_variant(variant: ProductVariant) -> VariantRead:
    return VariantRead(
        id=variant.id,
        tenant_id=variant.tenant_id,
        product_id=variant.product_id,
        sku=variant.sku,
        name=variant.name,
        price=variant.price,
        status=CatalogueStatus(variant.status),
        sale_price=variant.sale_price,
        sale_starts_at=variant.sale_starts_at,
        sale_ends_at=variant.sale_ends_at,
        effective_price=effective_price(variant),
        is_on_sale=is_on_sale(variant),
        options=variant_options(variant),
        inventory=(
            inventory_status(variant.inventory) if variant.inventory else None
        ),
    )


def _public_variants(product: Product) -> list[ProductVariant]:
    return [
        variant
        for variant in product.variants
        if variant.status == CatalogueStatus.ACTIVE.value
    ]


def storefront_variant(variant: ProductVariant) -> VariantStorefrontRead:
    sellable = sellable_quantity(variant.inventory)
    on_sale = is_on_sale(variant)
    return VariantStorefrontRead(
        id=variant.id,
        product_id=variant.product_id,
        sku=variant.sku,
        name=variant.name,
        price=effective_price(variant),
        compare_at_price=variant.price if on_sale else None,
        sale_ends_at=variant.sale_ends_at if on_sale else None,
        options=variant_options(variant),
        in_stock=sellable > 0,
        available_quantity=sellable,
    )


def storefront_options(product: Product) -> list[StorefrontOption]:
    """Every option and the values its sellable variants offer."""
    values: dict[str, list[str]] = {option.name: [] for option in product.options}

    for variant in _public_variants(product):
        for name, value in variant_options(variant).items():
            bucket = values.setdefault(name, [])
            if value not in bucket:
                bucket.append(value)

    return [
        StorefrontOption(name=option.name, values=values.get(option.name, []))
        for option in product.options
        if values.get(option.name)
    ]


def _price_range(
    variants: list[ProductVariant],
) -> tuple[Decimal | None, Decimal | None]:
    prices = [effective_price(variant) for variant in variants]
    if not prices:
        return None, None
    return min(prices), max(prices)


def _primary_image(product: Product) -> ProductImageStorefrontRead | None:
    if not product.images:
        return None
    chosen = next(
        (image for image in product.images if image.is_primary), product.images[0]
    )
    return ProductImageStorefrontRead.model_validate(chosen)


def storefront_summary(product: Product) -> ProductSummaryStorefrontRead:
    variants = _public_variants(product)
    price_from, price_to = _price_range(variants)

    return ProductSummaryStorefrontRead(
        id=product.id,
        slug=product.slug,
        category_id=product.category_id,
        name=product.name,
        short_description=product.short_description,
        brand=product.brand,
        fabric=product.fabric,
        occasion=product.occasion,
        sleeve=product.sleeve,
        neckline=product.neckline,
        is_featured=product.is_featured,
        primary_image=_primary_image(product),
        price_from=price_from,
        price_to=price_to,
        on_sale=any(is_on_sale(v) for v in variants),
        in_stock=any(sellable_quantity(v.inventory) > 0 for v in variants),
    )


def storefront_product(product: Product, category: Category) -> ProductStorefrontRead:
    variants = _public_variants(product)
    price_from, price_to = _price_range(variants)

    return ProductStorefrontRead(
        id=product.id,
        slug=product.slug,
        category=CategoryStorefrontRead.model_validate(category),
        name=product.name,
        short_description=product.short_description,
        description=product.description,
        brand=product.brand,
        fabric=product.fabric,
        occasion=product.occasion,
        sleeve=product.sleeve,
        neckline=product.neckline,
        fabric_details=product.fabric_details,
        washing_instructions=product.washing_instructions,
        country_of_origin=product.country_of_origin,
        size_chart=render_size_chart(product.size_chart),
        is_featured=product.is_featured,
        seo_title=product.seo_title,
        seo_description=product.seo_description,
        images=[
            ProductImageStorefrontRead.model_validate(image) for image in product.images
        ],
        options=storefront_options(product),
        variants=[storefront_variant(variant) for variant in variants],
        price_from=price_from,
        price_to=price_to,
        on_sale=any(is_on_sale(v) for v in variants),
        in_stock=any(sellable_quantity(v.inventory) > 0 for v in variants),
    )


def filter_options_read(options: dict[str, list[tuple[str, int]]]) -> FilterOptionsRead:
    return FilterOptionsRead(
        **{
            name: [FilterValueCount(value=value, count=count) for value, count in values]
            for name, values in options.items()
        }
    )
