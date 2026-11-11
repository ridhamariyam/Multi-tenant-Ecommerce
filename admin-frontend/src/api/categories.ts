import type { Category } from "../types/catalogue";
import { request } from "./client";

export type CategoryInput = Partial<Omit<Category, "id" | "tenant_id">> & { name?: string };

export const listCategories = (query: object = {}) =>
  request<Category[]>("/catalogue/categories", { query: { page_size: 100, ...query } });
export const createCategory = (data: CategoryInput) =>
  request<Category>("/catalogue/categories", { method: "POST", body: data });
export const updateCategory = (id: string, data: CategoryInput) =>
  request<Category>(`/catalogue/categories/${id}`, { method: "PATCH", body: data });
export const archiveCategory = (id: string) =>
  request<null>(`/catalogue/categories/${id}`, { method: "DELETE" });
