import type { ProductImage } from "../types/catalogue";
import { request } from "./client";

export const listImages = (productId: string) =>
  request<ProductImage[]>(`/catalogue/products/${productId}/images`);
export const addImageUrl = (productId: string, url: string, altText: string | null) =>
  request<ProductImage>(`/catalogue/products/${productId}/images`, {
    method: "POST",
    body: { url, alt_text: altText },
  });
export function uploadImage(productId: string, file: File, altText: string | null) {
  const form = new FormData();
  form.append("file", file);
  if (altText) form.append("alt_text", altText);
  return request<ProductImage>(`/catalogue/products/${productId}/images/upload`, {
    method: "POST",
    formData: form,
  });
}
export const reorderImages = (productId: string, order: { id: string; sort_order: number }[]) =>
  request<ProductImage[]>(`/catalogue/products/${productId}/images/order`, {
    method: "PUT",
    body: { images: order },
  });
export const makePrimary = (imageId: string) =>
  request<ProductImage>(`/catalogue/images/${imageId}/primary`, { method: "POST" });
export const deleteImage = (imageId: string) =>
  request<null>(`/catalogue/images/${imageId}`, { method: "DELETE" });
