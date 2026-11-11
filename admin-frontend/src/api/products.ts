import type {
  AttributeName,
  AttributeValue,
  ImportResult,
  Product,
  ProductFields,
  RelatedProduct,
} from "../types/catalogue";
import { download, request } from "./client";

export const listProducts = (query: object) => request<Product[]>("/catalogue/products", { query });
export const getProduct = (id: string) => request<Product>(`/catalogue/products/${id}`);
export const createProduct = (data: ProductFields & { images: { url: string; alt_text: string | null; is_primary: boolean; sort_order: number }[] }) =>
  request<Product>("/catalogue/products", { method: "POST", body: data });
export const updateProduct = (id: string, data: Partial<ProductFields>) =>
  request<Product>(`/catalogue/products/${id}`, { method: "PATCH", body: data });
export const archiveProduct = (id: string) =>
  request<null>(`/catalogue/products/${id}`, { method: "DELETE" });
export const getRelated = (id: string) =>
  request<RelatedProduct[]>(`/catalogue/products/${id}/related`);
export const setRelated = (id: string, productIds: string[]) =>
  request<RelatedProduct[]>(`/catalogue/products/${id}/related`, {
    method: "PUT",
    body: { product_ids: productIds },
  });

export const listAttributeValues = (query: object = {}) =>
  request<AttributeValue[]>("/catalogue/attributes", { query });
export const createAttributeValue = (attribute: AttributeName, value: string) =>
  request<AttributeValue>("/catalogue/attributes", { method: "POST", body: { attribute, value } });
export const updateAttributeValue = (id: string, data: Partial<Pick<AttributeValue, "value" | "is_active">>) =>
  request<AttributeValue>(`/catalogue/attributes/${id}`, { method: "PATCH", body: data });

/** Upload a photo before the product exists; the URL goes into the product's images. */
export function uploadUnattachedImage(file: File) {
  const form = new FormData();
  form.append("file", file);
  return request<{ url: string }>("/catalogue/images/upload", { method: "POST", formData: form });
}

export function importProducts(file: File, dryRun: boolean) {
  const form = new FormData();
  form.append("file", file);
  form.append("dry_run", String(dryRun));
  return request<ImportResult>("/catalogue/products/import", { method: "POST", formData: form });
}
export const downloadImportTemplate = (format: "xlsx" | "csv" = "xlsx") =>
  download("/catalogue/products/import/template", { format }, `product-import-template.${format}`);
