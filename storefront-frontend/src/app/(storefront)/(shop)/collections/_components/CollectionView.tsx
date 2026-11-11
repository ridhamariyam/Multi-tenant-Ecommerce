import type { Metadata } from 'next';
import Link from 'next/link';
import { notFound } from 'next/navigation';

import MobileBottomNav from '@/components/luxe/MobileBottomNav';
import { catalogueApi } from '@/lib/api/catalogue';
import { searchApi } from '@/lib/api/search';
import { categorySlug } from '@/lib/catalogue/slug';
import { sizeLabel } from '@/lib/catalogue/size';
import type { CategoryStorefront, ProductSort, ProductSummaryStorefront } from '@/types/catalogue';

import homeStyles from '../../../(home)/home/_components/luxe/Home.module.css';
import CollectionCard from './CollectionCard';
import CollectionToolbar from './CollectionToolbar';
import styles from './Collection.module.css';
import {
  type CollectionFilters,
  type CollectionSort,
  DEFAULT_SORT,
  EMPTY_FILTERS,
  activeFilterCount,
  PRODUCTS_COLLECTION_SLUG,
  collectionPath,
  cleanPrice,
  collectionQuery,
  isCollectionSort,
  splitList,
} from './collectionQuery';

const PAGE_SIZE = 12;
/** One backend page covers the whole (small) catalogue, the same bound the
 *  shop listing uses; the variant facets below can only be joined on a
 *  complete set. */
const CATALOGUE_FETCH_SIZE = 100;

const SIZE_ORDER = ['XXS', 'XS', 'S', 'M', 'L', 'XL', 'XXL', 'XXXL'];

export type CollectionSearchParams = {
  sort?: string;
  min_price?: string;
  max_price?: string;
  color?: string;
  size?: string;
  page?: string;
};

async function findCategory(slug: string): Promise<CategoryStorefront | undefined> {
  const categories = await catalogueApi.listCategories({ page_size: CATALOGUE_FETCH_SIZE });
  return categories.items.find(item => categorySlug(item.name) === slug);
}

/** Page metadata for the collection with this slug. */
export async function collectionMetadata(slug: string): Promise<Metadata> {
  if (slug === PRODUCTS_COLLECTION_SLUG) {
    return { title: 'Shop | CliQ.', description: 'Shop every CliQ collection.' };
  }
  const category = await findCategory(slug).catch(() => undefined);
  if (!category) return { title: 'Collection | CliQ.' };
  return {
    title: `${category.name} | CliQ.`,
    description: category.description ?? `Shop the CliQ ${category.name} collection.`,
  };
}

function toBackendSort(sort: CollectionSort): ProductSort {
  // "Featured" is the newest-first list with featured pieces lifted to the top.
  return sort === 'featured' ? 'newest' : sort;
}

function bySizeOrder(a: string, b: string): number {
  const ai = SIZE_ORDER.indexOf(a.toUpperCase());
  const bi = SIZE_ORDER.indexOf(b.toUpperCase());
  if (ai !== -1 && bi !== -1) return ai - bi;
  if (ai !== -1) return -1;
  if (bi !== -1) return 1;
  return a.localeCompare(b);
}

function intersects(selected: string[], values: Set<string> | undefined): boolean {
  return selected.length === 0 || (!!values && selected.some(value => values.has(value)));
}

/**
 * The collection listing, shared by /collections/[slug] (one category) and
 * /products (the whole catalogue, see `collectionPath`).
 */
export default async function CollectionView({ slug, query }: { slug: string; query: CollectionSearchParams }) {
  const categoriesPage = await catalogueApi.listCategories({ page_size: CATALOGUE_FETCH_SIZE });
  const showAll = slug === PRODUCTS_COLLECTION_SLUG;
  const category = categoriesPage.items.find(item => categorySlug(item.name) === slug);
  if (!showAll && !category) notFound();

  const title = category?.name ?? 'Shop';
  const description = category?.description ?? (showAll ? 'Every piece in the collection.' : null);

  const sort: CollectionSort = isCollectionSort(query.sort) ? query.sort : DEFAULT_SORT;
  const requestedPage = Math.max(1, Number(query.page ?? 1) || 1);

  const [listing, catalogue, variantSource] = await Promise.all([
    // Sort and price are applied by the backend.
    catalogueApi.listProducts({
      page_size: CATALOGUE_FETCH_SIZE,
      category_id: category?.id,
      sort: toBackendSort(sort),
      min_price: cleanPrice(query.min_price) || undefined,
      max_price: cleanPrice(query.max_price) || undefined,
    }),
    // Unfiltered catalogue: drives the Category facet and the price bounds.
    catalogueApi.listProducts({ page_size: CATALOGUE_FETCH_SIZE }),
    // Color/Size only exist as variant options on the search endpoint. If it
    // is unavailable those facets are hidden rather than shown empty.
    searchApi.searchProducts({ category_id: category?.id, size: CATALOGUE_FETCH_SIZE }).catch(() => null),
  ]);

  const colorsById = new Map<string, Set<string>>();
  const sizesById = new Map<string, Set<string>>();
  for (const item of variantSource?.items ?? []) {
    const colors = new Set(item.variants.map(v => v.options.Color).filter((c): c is string => !!c));
    const sizes = new Set(item.variants.map(v => v.options.Size).filter((s): s is string => !!s).map(sizeLabel));
    if (colors.size) colorsById.set(item.id, colors);
    if (sizes.size) sizesById.set(item.id, sizes);
  }
  const colorOptions = [...new Set([...colorsById.values()].flatMap(set => [...set]))].sort((a, b) =>
    a.localeCompare(b),
  );
  const sizeOptions = [...new Set([...sizesById.values()].flatMap(set => [...set]))].sort(bySizeOrder);

  // Values not offered by this collection are dropped, so a stale link can't
  // leave an invisible filter applied.
  const filters: CollectionFilters = {
    minPrice: cleanPrice(query.min_price),
    maxPrice: cleanPrice(query.max_price),
    colors: splitList(query.color).filter(value => colorOptions.includes(value)),
    sizes: splitList(query.size).filter(value => sizeOptions.includes(value)),
  };

  let products: ProductSummaryStorefront[] = listing.items.filter(
    product =>
      intersects(filters.colors, colorsById.get(product.id)) &&
      intersects(filters.sizes, sizesById.get(product.id)),
  );
  if (sort === 'featured') {
    products = [...products].sort((a, b) => Number(b.is_featured) - Number(a.is_featured));
  }

  const total = products.length;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.min(requestedPage, pageCount);
  const visible = products.slice(0, page * PAGE_SIZE);

  // A product counts towards its category and every ancestor, matching the
  // backend, whose category listing includes all sub-categories.
  const parentOf = new Map(categoriesPage.items.map(item => [item.id, item.parent_id ?? null]));
  const productCountByCategory = new Map<string, number>();
  for (const product of catalogue.items) {
    for (let id: string | null = product.category_id; id; id = parentOf.get(id) ?? null) {
      productCountByCategory.set(id, (productCountByCategory.get(id) ?? 0) + 1);
    }
  }
  const categoryOptions = categoriesPage.items
    .filter(item => productCountByCategory.has(item.id))
    .map(item => ({
      name: item.name,
      href: collectionPath(categorySlug(item.name)),
      count: productCountByCategory.get(item.id) ?? 0,
      active: item.id === category?.id,
    }));

  const prices = catalogue.items
    .filter(product => !category || product.category_id === category.id)
    .flatMap(product => [product.price_from, product.price_to])
    .map(Number)
    .filter(value => Number.isFinite(value) && value > 0);
  const priceBounds = prices.length
    ? { min: Math.floor(Math.min(...prices)), max: Math.ceil(Math.max(...prices)) }
    : null;

  const basePath = collectionPath(slug);
  const filtered = activeFilterCount(filters) > 0;

  return (
    <div className={`${homeStyles.page} ${styles.page}`}>
      <section className={`${homeStyles.container} ${styles.intro}`}>
        <nav className={styles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">{title}</span>
        </nav>
        <h1 className={styles.title}>{title}</h1>
        {description && <p className={styles.description}>{description}</p>}
      </section>

      <section className={`${homeStyles.container} ${styles.listing}`} aria-label={`${title} products`}>
        <CollectionToolbar
          basePath={basePath}
          sort={sort}
          filters={filters}
          shown={visible.length}
          total={total}
          categories={categoryOptions}
          colorOptions={colorOptions}
          sizeOptions={sizeOptions}
          priceBounds={priceBounds}
        />

        {visible.length === 0 ? (
          <div className={styles.empty}>
            <p>{filtered ? 'No products match these filters.' : `No ${title.toLowerCase()} available yet.`}</p>
            {filtered && (
              <Link href={`${basePath}${collectionQuery(sort, EMPTY_FILTERS)}`} className={styles.outlineButton}>
                Clear all
              </Link>
            )}
          </div>
        ) : (
          <div className={styles.grid}>
            {visible.map((product, index) => (
              <CollectionCard
                key={product.id}
                product={product}
                colors={[...(colorsById.get(product.id) ?? [])]}
                priority={index < 4}
              />
            ))}
          </div>
        )}

        {visible.length < total && (
          <div className={styles.loadMore}>
            <p className={styles.loadMoreCount}>
              Showing {visible.length} of {total} products
            </p>
            <div className={styles.progress} aria-hidden="true">
              <span style={{ width: `${(visible.length / total) * 100}%` }} />
            </div>
            <Link
              href={`${basePath}${collectionQuery(sort, filters, page + 1)}`}
              scroll={false}
              className={styles.outlineButton}
            >
              Load more
            </Link>
          </div>
        )}
      </section>

      <MobileBottomNav />
    </div>
  );
}
