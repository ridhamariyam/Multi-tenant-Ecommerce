import { request } from "./client";

export interface LookPin { product_id: string; product_name?: string; product_slug?: string; x: number; y: number }
export interface Look {
  id: string;
  title: string;
  slug: string;
  description: string | null;
  cover_url: string | null;
  status: "DRAFT" | "PUBLISHED" | "ARCHIVED";
  pins: LookPin[];
  published_at: string | null;
}
export type LookWrite = { title: string; description?: string | null; cover_url: string | null; pins: { product_id: string; x: number; y: number }[] };

export const listLooks = () => request<Look[]>("/admin/looks");
export const createLook = (body: LookWrite) => request<Look>("/admin/looks", { method: "POST", body });
export const updateLook = (id: string, body: LookWrite) => request<Look>(`/admin/looks/${encodeURIComponent(id)}`, { method: "PUT", body });
export const publishLook = (id: string, published: boolean) =>
  request<Look>(`/admin/looks/${encodeURIComponent(id)}/publish`, { method: "POST", body: { published } });
export const archiveLook = (id: string) => request<null>(`/admin/looks/${encodeURIComponent(id)}`, { method: "DELETE" });
