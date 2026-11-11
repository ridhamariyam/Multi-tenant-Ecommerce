import type { GstDefaults, GstReport, GstSettings, ProductTaxReview, TaxRateConfiguration, TaxRateTargets, TaxSettings } from "../types/settings";
import { request } from "./client";

export const getTax = () => request<TaxSettings>("/admin/tax");
export const updateTax = (data: Pick<TaxSettings, "tax_percentage" | "is_active">) => request<TaxSettings>("/admin/tax", { method: "PUT", body: data });
export const confirmTax = () => request<TaxSettings>("/admin/tax/confirm", { method: "POST", body: { ca_confirmed: true } });
export const getGst = () => request<GstSettings>("/admin/gst");
export const updateGst = (data: Partial<GstSettings>) =>
  request<GstSettings>("/admin/gst", { method: "PUT", body: data });
export const activateGst = () => request<GstSettings>("/admin/gst/activate", { method: "POST", body: { ca_confirmed: true } });
export const listTaxRates = () => request<TaxRateConfiguration[]>("/admin/gst/rates");
export const getTaxRateTargets = () => request<TaxRateTargets>("/admin/gst/targets");
export const createTaxRate = (data: { product_id?: string; category_id?: string; hsn_code: string; gst_rate: string; effective_from: string }) =>
  request<TaxRateConfiguration>("/admin/gst/rates", { method: "POST", body: data });
export const approveTaxRate = (id: string) => request<TaxRateConfiguration>(`/admin/gst/rates/${id}/approve`, { method: "POST", body: { ca_confirmed: true } });
export const getGstReport = (start_date: string, end_date: string) =>
  request<GstReport>("/admin/gst/report", { query: { start_date, end_date } });
export const getGstDefaults = () => request<GstDefaults>("/admin/gst/defaults");
export const reviewGstDefaults = (reviewed: boolean) => request<GstDefaults>("/admin/gst/defaults/review", { method: "POST", body: { reviewed } });
export const getProductTaxReview = (flagged: boolean) =>
  request<ProductTaxReview[]>("/admin/gst/product-review", { query: { flagged: String(flagged) } });
