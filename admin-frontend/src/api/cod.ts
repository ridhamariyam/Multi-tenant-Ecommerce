import type { CodCollection, CodSettings } from "../types/settings";
import { request } from "./client";

export const getCodSettings = () => request<CodSettings>("/admin/cod/settings");
export const updateCodSettings = (data: CodSettings) =>
  request<CodSettings>("/admin/cod/settings", { method: "PUT", body: data });
export const getCodReport = (start_date: string, end_date: string) =>
  request<Record<string, string | number>>("/admin/cod/report", { query: { start_date, end_date } });
export const listCollections = (query: object) => request<CodCollection[]>("/admin/cod/collections", { query });
export const recordRemittance = (payment_ids: string[], reference: string, remitted_on: string | null) =>
  request<{ remitted: number; amount: string }>("/admin/cod/remittances", {
    method: "POST",
    body: { payment_ids, reference, remitted_on },
  });
