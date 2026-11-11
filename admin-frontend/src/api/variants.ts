import type { InventoryMovement, InventoryStatus, Variant, VariantInput } from "../types/catalogue";
import { request } from "./client";

export const listVariants = (productId: string) =>
  request<Variant[]>(`/catalogue/products/${productId}/variants`, { query: { page_size: 100 } });
export const createVariant = (productId: string, data: VariantInput & { initial_quantity: number; low_stock_threshold: number }) =>
  request<Variant>(`/catalogue/products/${productId}/variants`, { method: "POST", body: data });
export const updateVariant = (id: string, data: Partial<VariantInput>) =>
  request<Variant>(`/catalogue/variants/${id}`, { method: "PATCH", body: data });
export const archiveVariant = (id: string) =>
  request<null>(`/catalogue/variants/${id}`, { method: "DELETE" });

const inv = (id: string) => `/catalogue/variants/${id}/inventory`;
export const setStock = (id: string, quantity: number, note: string | null) =>
  request<InventoryStatus>(inv(id), { method: "PUT", body: { available_quantity: quantity, note } });
export const adjustStock = (id: string, delta: number, reason: string, note: string | null) =>
  request<InventoryStatus>(`${inv(id)}/adjust`, { method: "POST", body: { delta, reason, note } });
export const setThreshold = (id: string, threshold: number) =>
  request<InventoryStatus>(`${inv(id)}/threshold`, { method: "PUT", body: { low_stock_threshold: threshold } });
export const listMovements = (id: string, page = 1) =>
  request<InventoryMovement[]>(`${inv(id)}/movements`, { query: { page, page_size: 20 } });
