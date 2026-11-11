export type CatalogueStatus = 'DRAFT' | 'ACTIVE' | 'ARCHIVED';

export type ProductGender = 'MEN' | 'WOMEN' | 'UNISEX';

/** Sort orders `/storefront/products` accepts. Search uses its own vocabulary. */
export type ProductSort = 'newest' | 'name_asc' | 'name_desc' | 'price_low' | 'price_high';

export interface CategoryStorefront {
  id: string;
  name: string;
  description: string | null;
  /** Set on a sub-category; a parent's listing includes its children's products. */
  parent_id?: string | null;
}

export interface ProductImageStorefront {
  id: string;
  url: string;
  alt_text: string | null;
  sort_order: number;
  is_primary: boolean;
}

export interface VariantStorefront {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  /** What the shopper pays now, sale included. */
  price: string;
  /** The regular price; set only while a sale is on. */
  compare_at_price?: string | null;
  sale_ends_at?: string | null;
  options: Record<string, string>;
  in_stock: boolean;
  available_quantity: number;
}

/** An option and the values an in-stock variant actually offers. */
export interface StorefrontOption {
  name: string;
  values: string[];
}

export interface ProductSummaryStorefront {
  id: string;
  slug?: string;
  category_id: string;
  name: string;
  short_description: string | null;
  brand: string | null;
  is_featured: boolean;
  primary_image: ProductImageStorefront | null;
  price_from: string | null;
  price_to: string | null;
  /** Sent by `/storefront/products`; carries no compare-at price to strike through. */
  on_sale?: boolean;
  in_stock: boolean;
}

/** One size's measurements, already converted to both units by the API. */
export interface SizeChartRow {
  size: string;
  values_in: Record<string, string>;
  values_cm: Record<string, string>;
}

export interface SizeChart {
  /** The unit the chart was entered in. */
  unit: 'in' | 'cm';
  measurements: string[];
  rows: SizeChartRow[];
  note: string | null;
}

export interface ProductStorefront {
  id: string;
  slug?: string;
  category: CategoryStorefront;
  name: string;
  short_description: string | null;
  description: string | null;
  brand: string | null;
  fabric?: string | null;
  occasion?: string | null;
  sleeve?: string | null;
  neckline?: string | null;
  fabric_details?: string | null;
  washing_instructions?: string | null;
  country_of_origin?: string | null;
  size_chart?: SizeChart | null;
  is_featured: boolean;
  seo_title: string | null;
  seo_description: string | null;
  images: ProductImageStorefront[];
  options: StorefrontOption[];
  variants: VariantStorefront[];
  price_from: string | null;
  price_to: string | null;
  on_sale?: boolean;
  in_stock: boolean;
}

export interface ProductListQuery {
  page?: number;
  page_size?: number;
  category_id?: string;
  search?: string;
  brand?: string;
  featured?: boolean;
  min_price?: string;
  max_price?: string;
  sort?: ProductSort;
}
