/**
 * URL contract for the collection page (`/collections/[slug]`), shared by
 * the server route that reads it and the client controls that write it.
 *
 * Multi-select facets (color, size) are comma-joined so a
 * filtered collection stays a short, shareable link.
 */

export const COLLECTION_SORTS = [
  { value: 'featured', label: 'Featured' },
  { value: 'newest', label: 'Newest' },
  { value: 'name_asc', label: 'Alphabetically, A-Z' },
  { value: 'name_desc', label: 'Alphabetically, Z-A' },
  { value: 'price_low', label: 'Price, Low To High' },
  { value: 'price_high', label: 'Price, High To Low' },
] as const;

export type CollectionSort = (typeof COLLECTION_SORTS)[number]['value'];

export const DEFAULT_SORT: CollectionSort = 'featured';

export interface CollectionFilters {
  minPrice: string;
  maxPrice: string;
  colors: string[];
  sizes: string[];
}

export const EMPTY_FILTERS: CollectionFilters = {
  minPrice: '',
  maxPrice: '',
  colors: [],
  sizes: [],
};

export function isCollectionSort(value: string | undefined): value is CollectionSort {
  return COLLECTION_SORTS.some(option => option.value === value);
}

export function splitList(value: string | undefined): string[] {
  return value ? value.split(',').map(part => part.trim()).filter(Boolean) : [];
}

/** Only a non-negative number survives; anything else reads as "no bound". */
export function cleanPrice(value: string | undefined): string {
  const trimmed = value?.trim() ?? '';
  return trimmed && Number.isFinite(Number(trimmed)) && Number(trimmed) >= 0 ? trimmed : '';
}

export function activeFilterCount(filters: CollectionFilters): number {
  return (
    filters.colors.length +
    filters.sizes.length +
    (filters.minPrice || filters.maxPrice ? 1 : 0)
  );
}

/** Query string for a collection state; defaults are left out of the URL. */
export function collectionQuery(sort: CollectionSort, filters: CollectionFilters, page = 1): string {
  const params = new URLSearchParams();
  if (sort !== DEFAULT_SORT) params.set('sort', sort);
  if (filters.minPrice) params.set('min_price', filters.minPrice);
  if (filters.maxPrice) params.set('max_price', filters.maxPrice);
  if (filters.colors.length) params.set('color', filters.colors.join(','));
  if (filters.sizes.length) params.set('size', filters.sizes.join(','));
  if (page > 1) params.set('page', String(page));
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/** The whole catalogue, served as the main product listing at /products. */
export const PRODUCTS_COLLECTION_SLUG = 'all';

/** Where a collection lives: /products for the main one, /collections/<slug> otherwise. */
export function collectionPath(slug: string): string {
  return slug === PRODUCTS_COLLECTION_SLUG ? '/products' : `/collections/${encodeURIComponent(slug)}`;
}
