import type { CatalogueStatus } from "./api";

export interface Category {
  id: string;
  tenant_id: string;
  parent_id: string | null;
  name: string;
  description: string | null;
  status: CatalogueStatus;
  hsn_code: string | null;
  gst_rate: string | null;
}

export type ProductGender = "MEN" | "WOMEN" | "UNISEX";

export interface ProductImage {
  id: string;
  product_id: string;
  url: string;
  alt_text: string | null;
  sort_order: number;
  is_primary: boolean;
}

export interface SizeChartRowInput {
  size: string;
  values: Record<string, string>;
}

export interface SizeChartInput {
  unit: "in" | "cm";
  measurements: string[];
  rows: SizeChartRowInput[];
  note: string | null;
}

export interface SizeChartRead {
  unit: "in" | "cm";
  measurements: string[];
  rows: { size: string; values_in: Record<string, string>; values_cm: Record<string, string> }[];
  note: string | null;
}

export interface Product {
  id: string;
  category_id: string;
  name: string;
  slug: string;
  short_description: string | null;
  description: string | null;
  brand: string | null;
  status: CatalogueStatus;
  gender: ProductGender | null;
  fabric: string | null;
  occasion: string | null;
  sleeve: string | null;
  neckline: string | null;
  fabric_details: string | null;
  washing_instructions: string | null;
  country_of_origin: string | null;
  size_chart: SizeChartRead | null;
  hsn_code: string | null;
  gst_rate: string | null;
  is_featured: boolean;
  seo_title: string | null;
  seo_description: string | null;
  images: ProductImage[];
  options: { id: string; name: string; position: number }[];
}

export interface ProductFields {
  category_id: string;
  name: string;
  slug?: string;
  short_description: string | null;
  description: string | null;
  brand: string | null;
  status: CatalogueStatus;
  gender: ProductGender | null;
  fabric: string | null;
  occasion: string | null;
  sleeve: string | null;
  neckline: string | null;
  fabric_details: string | null;
  washing_instructions: string | null;
  country_of_origin: string | null;
  size_chart: SizeChartInput | null;
  hsn_code: string | null;
  gst_rate: string | null;
  is_featured: boolean;
  seo_title: string | null;
  seo_description: string | null;
}

export interface InventoryStatus {
  variant_id: string;
  available_quantity: number;
  reserved_quantity: number;
  low_stock_threshold: number;
  sellable_quantity: number;
  is_low_stock: boolean;
}

export interface Variant {
  id: string;
  product_id: string;
  sku: string;
  name: string;
  price: string;
  status: CatalogueStatus;
  sale_price: string | null;
  sale_starts_at: string | null;
  sale_ends_at: string | null;
  effective_price: string | null;
  is_on_sale: boolean;
  options: Record<string, string>;
  inventory: InventoryStatus | null;
}

export interface VariantInput {
  sku: string;
  name: string;
  price: string;
  status: CatalogueStatus;
  options: { name: string; value: string }[];
  sale_price: string | null;
  sale_starts_at: string | null;
  sale_ends_at: string | null;
}

export interface InventoryMovement {
  id: string;
  variant_id: string;
  delta: number;
  reason: string;
  reference: string | null;
  note: string | null;
}

export interface RelatedProduct {
  id: string;
  name: string;
  status: CatalogueStatus;
  position: number;
}

export type AttributeName = "fabric" | "occasion" | "sleeve" | "neckline";
export const ATTRIBUTE_NAMES: AttributeName[] = ["fabric", "occasion", "sleeve", "neckline"];

export interface AttributeValue {
  id: string;
  attribute: AttributeName;
  value: string;
  is_active: boolean;
  position: number;
  product_count: number;
}

export interface ImportResult {
  rows: number;
  products: number;
  variants: number;
  dry_run: boolean;
  errors: { row: number; message: string }[];
}
