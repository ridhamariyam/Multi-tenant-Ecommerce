import type { StockItem } from "../../types/dashboard";

export const DASHBOARD_PAGE_SIZE = 50;
export type { SalesTrendPoint as TrendPoint } from "../../types/dashboard";
export interface SalesRow { period: string; orders: number; revenue: string; average_order_value: string }
export interface SalesReport { rows: SalesRow[]; summary: { orders: number; revenue: string; average_order_value: string }; currency: string }
export interface InventoryRow extends StockItem { sellable_quantity: number; stock_status: "LOW" | "OUT_OF_STOCK" | "IN_STOCK" }

export function inventoryProducts(rows: InventoryRow[]) {
  const variants = [...new Map(rows.map((row) => [row.variant_id ?? `${row.product_id}:${row.sku}`, row])).values()];
  const products = new Map<string, { id: string; name: string; available: number; sellable: number; low: boolean; out: boolean }>();
  for (const row of variants) {
    const product = products.get(row.product_id) ?? { id: row.product_id, name: row.product_name, available: 0, sellable: 0, low: false, out: false };
    product.available += row.available_quantity;
    product.sellable += row.sellable_quantity;
    product.low ||= row.stock_status === "LOW";
    product.out ||= row.stock_status === "OUT_OF_STOCK";
    products.set(row.product_id, product);
  }
  return [...products.values()];
}

// Backend dashboard/report periods use UTC, so date filters use the same boundary.
export function utcDate(daysAgo = 0): string {
  const date = new Date();
  date.setUTCDate(date.getUTCDate() - daysAgo);
  return date.toISOString().slice(0, 10);
}
