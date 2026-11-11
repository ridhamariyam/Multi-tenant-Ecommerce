import { request } from "./client";

export interface AiOutput { id: string; url: string | null; review_status: string | null; width: number | null; height: number | null }
export interface AiJob {
  id: string;
  product_id: string;
  virtual_model_id: string;
  status: "queued" | "starting" | "processing" | "completed" | "failed" | "cancelled";
  resolution: string;
  generation_mode: string;
  num_images: number;
  credits_reserved: number;
  credits_charged: number | null;
  error_message: string | null;
  created_at: string;
  finished_at: string | null;
  provider: string;
  outputs: AiOutput[];
}
export interface AiCredits {
  balance: number;
  configured: boolean;
  provider: string | null;
  price_table: Record<string, number>;
  ledger: { type: string; credits: number; note: string | null; at: string }[];
}
export interface VirtualModel { id: string; name: string; description: string | null; gender_presentation: string; image_url: string | null }

export const aiCredits = () => request<AiCredits>("/admin/ai/credits");
export const listAiJobs = () => request<AiJob[]>("/admin/ai/jobs", { query: { limit: 30 } });
export const createAiJob = (
  body: { product_id: string; virtual_model_id: string; resolution: string; generation_mode: string; num_images: number },
  idempotencyKey: string,
) => request<AiJob>("/admin/ai/jobs", { method: "POST", body, headers: { "Idempotency-Key": idempotencyKey } });
export const retryAiJob = (id: string) => request<AiJob>(`/admin/ai/jobs/${encodeURIComponent(id)}/retry`, { method: "POST" });
export const cancelAiJob = (id: string) => request<AiJob>(`/admin/ai/jobs/${encodeURIComponent(id)}/cancel`, { method: "POST" });
export const reviewAiOutput = (id: string, decision: "APPROVED" | "REJECTED") =>
  request<AiOutput>(`/admin/ai/outputs/${encodeURIComponent(id)}/review`, { method: "POST", body: { decision, add_to_product: true } });
export const listVirtualModels = () => request<VirtualModel[]>("/platform/virtual-models");
