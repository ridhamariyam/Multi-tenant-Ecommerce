import type { Payment } from "../types/order";
import { request } from "./client";

export const listPayments = (query: object) => request<Payment[]>("/admin/payments", { query });
export const markAdvancePaid = (id: string) =>
  request<Payment>(`/admin/payments/${id}/mark-paid`, { method: "POST" });
