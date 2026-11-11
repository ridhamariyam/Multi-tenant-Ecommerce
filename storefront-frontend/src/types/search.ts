/** Sort orders `/storefront/search-products` accepts. Anything else is a 422. */
export type SearchSort = 'RECOMMENDED' | 'NEWEST' | 'price' | '-price';

export interface VariantAttributes {
  variant_id: string;
  options: Record<string, string>;
}

/**
 * A search result row. Carries no image and no stock flag, so a grid that
 * renders cards needs `/storefront/products` as well.
 */
export interface ProductDiscoveryItem {
  id: string;
  name: string;
  brand: string | null;
  gender: string | null;
  category_id: string;
  price: string | null;
  min_price: string | null;
  max_price: string | null;
  rating: number | null;
  variants: VariantAttributes[];
}

export interface SuggestionItem {
  title: string;
}

/** Search pages with `size`, not `page_size`. */
export interface SearchQuery {
  q?: string;
  category_id?: string;
  gender?: string;
  brand?: string;
  min_price?: string;
  max_price?: string;
  color?: string;
  product_size?: string;
  min_rating?: number;
  max_rating?: number;
  sort?: SearchSort;
  page?: number;
  size?: number;
}
