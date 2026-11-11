import type { Payment } from "../types/order";
import { request } from "./client";

export const listPayments = (query: object) => request<Payment[]>("/admin/payments", { query });
export const markAdvancePaid = (id: string) =>
  request<Payment>(`/admin/payments/${id}/mark-paid`, { method: "POST" });

export interface PaymentGateway {
  source: "own" | "platform" | "none";
  connected: boolean;
  is_enabled: boolean;
  key_id: string | null;
  mode: "live" | "test" | null;
  has_webhook_secret: boolean;
  verified_at: string | null;
  webhook_url: string;
}

export const getPaymentGateway = () => request<PaymentGateway>("/admin/payment-gateway");
export const savePaymentGateway = (body: { key_id: string; key_secret?: string | null; webhook_secret?: string | null; is_enabled: boolean }) =>
  request<PaymentGateway>("/admin/payment-gateway", { method: "PUT", body });
export const disconnectPaymentGateway = () => request<PaymentGateway>("/admin/payment-gateway", { method: "DELETE" });
