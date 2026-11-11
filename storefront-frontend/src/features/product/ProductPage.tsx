import Link from 'next/link';
import { notFound, permanentRedirect } from 'next/navigation';

import CollectionCard from '@/app/(storefront)/(shop)/collections/_components/CollectionCard';
import { collectionPath } from '@/app/(storefront)/(shop)/collections/_components/collectionQuery';
import ProductReviews from '@/elements/SingleProductPage/ProductReviews';
import ProductDetails from '@/elements/SingleProductPage/luxe/ProductDetails';
import ProductGallery from '@/elements/SingleProductPage/luxe/ProductGallery';
import { catalogueApi } from '@/lib/api/catalogue';
import { ApiError } from '@/lib/api/errors';
import { reviewApi } from '@/lib/api/reviews';
import { getCurrentUser } from '@/lib/auth/current-user';
import { categorySlug } from '@/lib/catalogue/slug';
import type { ProductStorefront } from '@/types/catalogue';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import styles from '@/elements/SingleProductPage/luxe/ProductDetails.module.css';

const RELATED_COUNT = 4;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const SingleProductPage = async ({
  params,
  searchParams,
}: {
  params: Promise<{ id?: string; slug?: string }>;
  searchParams?: Promise<{ variant?: string }>;
}) => {
  const { id, slug } = await params;
  const { variant } = (await searchParams) ?? {};
  const productKey = id ?? slug;
  if (!productKey) notFound();

  let product: ProductStorefront;

  try {
    // Cart lines, wishlist items and orders only know the product id, so
    // /products/<id> is accepted too and sent on to the slug URL below.
    product = slug && !UUID.test(slug) ? await catalogueApi.getProductBySlug(slug) : await catalogueApi.getProduct(productKey);
  } catch (error) {
    // A malformed id can never match a product, so it is a 404 rather than a crash.
    if (error instanceof ApiError && (error.isNotFound || error.code === 'VALIDATION_ERROR')) notFound();
    throw error;
  }

  if (product.slug && productKey !== product.slug) {
    const query = variant ? `?variant=${encodeURIComponent(variant)}` : '';
    permanentRedirect(`/products/${encodeURIComponent(product.slug)}${query}`);
  }

  /* A product with no reviews still renders, with an empty star row, and
     "you might also like" falls back to nothing rather than to filler. */
  const [summary, related, reviews, user] = await Promise.all([
    reviewApi.summary(product.id).catch(() => null),
    catalogueApi
      .listProducts({ category_id: product.category.id, page_size: RELATED_COUNT + 1 })
      .then(page => page.items.filter(item => item.id !== product.id).slice(0, RELATED_COUNT))
      .catch(() => []),
    reviewApi
      .listForProduct(product.id, { page_size: 20 })
      .then(page => page.items)
      .catch(() => []),
    getCurrentUser().catch(() => null),
  ]);

  const images = [...product.images].sort(
    (a, b) => Number(b.is_primary) - Number(a.is_primary) || a.sort_order - b.sort_order,
  );

  return (
    <div className={homeStyles.page}>
      <div className={homeStyles.container}>
        <nav className={styles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <Link href={collectionPath(categorySlug(product.category.name))}>
            {product.category.name}
          </Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{product.name}</span>
        </nav>

        <div className={styles.layout}>
          <div className={styles.galleryColumn}>
            <ProductGallery images={images} productName={product.name} />
          </div>
          <div className={styles.detailsColumn}>
            <ProductDetails product={product} initialVariantId={variant} />
          </div>
        </div>
      </div>

      {related.length > 0 && (
        <section className={`${homeStyles.container} ${styles.related}`} aria-labelledby="related-title">
          <h2 id="related-title" className={styles.relatedTitle}>
            We think you&apos;d like
          </h2>
          <div className={styles.relatedGrid}>
            {related.map(item => (
              <CollectionCard key={item.id} product={item} colors={[]} />
            ))}
          </div>
        </section>
      )}

      <ProductReviews productId={product.id} productName={product.name} reviews={reviews} summary={summary} currentUserId={user?.id ?? null} />
    </div>
  );
};

export default SingleProductPage;
