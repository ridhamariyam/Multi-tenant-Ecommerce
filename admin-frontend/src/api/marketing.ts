import { request } from "./client";

export type SegmentKind = "ALL" | "ORDERED_WITHIN" | "NO_ORDERS" | "TAG";
export interface Segment { kind: SegmentKind; days?: number | null; tag?: string | null }
export interface Campaign {
  id: string;
  name: string;
  subject: string;
  body: string;
  segment: Segment;
  status: "DRAFT" | "SENT";
  recipients: number;
  sent_at: string | null;
  created_at: string;
  audience: number | null;
}

export const marketingSummary = () => request<{ customers: number; subscribed: number }>("/admin/marketing/summary");
export const segmentAudience = (segment: Segment) =>
  request<{ count: number }>("/admin/marketing/audience", { method: "POST", body: segment });
export const listCampaigns = () => request<Campaign[]>("/admin/marketing/campaigns");
export const createCampaign = (body: { name: string; subject: string; body: string; segment: Segment }) =>
  request<Campaign>("/admin/marketing/campaigns", { method: "POST", body });
export const sendCampaign = (id: string) =>
  request<Campaign>(`/admin/marketing/campaigns/${encodeURIComponent(id)}/send`, { method: "POST" });
