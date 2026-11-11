import type { Metadata } from 'next';

import { collectionPath } from '@/app/(storefront)/(shop)/collections/_components/collectionQuery';
import { categorySlug } from '@/lib/catalogue/slug';
import { mediaUrl } from '@/lib/media';
import { absoluteUrl, DEFAULT_OG_IMAGE, JsonLd, plainText, withoutBrand } from '@/lib/seo';
import type { ProductStorefront } from '@/types/catalogue';
import type { RatingSummary } from '@/types/reviews';

function orderedImages(product: ProductStorefront) {
  return [...product.images].sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary) || a.sort_order - b.sort_order,
  );
}

function describe(product: ProductStorefront, storeName: string): string {
  return (
    plainText(product.seo_description) ||
    plainText(product.short_description) ||
    plainText(product.description) ||
    `Shop ${product.name} from ${storeName}.`
  );
}

export function productPath(product: ProductStorefront): string {
  return `/products/${encodeURIComponent(product.slug ?? product.id)}`;
}

/** Title, description, canonical link and share card for a product page. */
export function productMetadata(product: ProductStorefront, storeName: string): Metadata {
  const description = describe(product, storeName);
  const title = withoutBrand(product.seo_title?.trim() || '', storeName) || product.name;
  const images = orderedImages(product)
    .slice(0, 4)
    .map(image => ({ url: mediaUrl(image.url), alt: image.alt_text || product.name }));

  return {
    title,
    description,
    alternates: { canonical: productPath(product) },
    openGraph: { type: 'website', title, description, url: productPath(product), images: images.length ? images : [DEFAULT_OG_IMAGE] },
    twitter: { card: 'summary_large_image', title, description, images: images.length ? images.map(image => image.url) : [DEFAULT_OG_IMAGE.url] },
  };
}

/** schema.org Product (with offers and rating) and BreadcrumbList, for rich results. */
export async function ProductJsonLd({
  product,
  summary,
  storeName,
}: {
  product: ProductStorefront;
  summary: RatingSummary | null;
  storeName: string;
}) {
  const url = await absoluteUrl(productPath(product));
  const collectionUrl = await absoluteUrl(collectionPath(categorySlug(product.category.name)));
  const home = await absoluteUrl('/');

  const offers = product.variants.map(variant => ({
    '@type': 'Offer',
    sku: variant.sku,
    name: variant.name,
    price: Number(variant.price).toFixed(2),
    priceCurrency: 'INR',
    availability: variant.in_stock ? 'https://schema.org/InStock' : 'https://schema.org/OutOfStock',
    itemCondition: 'https://schema.org/NewCondition',
    url: `${url}?variant=${encodeURIComponent(variant.id)}`,
  }));

  const productLd: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'Product',
    name: product.name,
    description: describe(product, storeName),
    image: orderedImages(product).map(image => mediaUrl(image.url)),
    url,
    sku: product.variants[0]?.sku,
    brand: { '@type': 'Brand', name: product.brand || storeName },
    category: product.category.name,
    ...(product.country_of_origin ? { countryOfOrigin: product.country_of_origin } : {}),
    ...(product.fabric ? { material: product.fabric } : {}),
    ...(offers.length ? { offers } : {}),
    ...(summary && summary.total_reviews > 0
      ? {
          aggregateRating: {
            '@type': 'AggregateRating',
            ratingValue: Number(summary.average_rating).toFixed(1),
            reviewCount: summary.total_reviews,
            bestRating: 5,
            worstRating: 1,
          },
        }
      : {}),
  };

  const breadcrumbs = {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: [
      { '@type': 'ListItem', position: 1, name: 'Home', item: home },
      { '@type': 'ListItem', position: 2, name: product.category.name, item: collectionUrl },
      { '@type': 'ListItem', position: 3, name: product.name, item: url },
    ],
  };

  return <JsonLd data={[productLd, breadcrumbs]} />;
}
