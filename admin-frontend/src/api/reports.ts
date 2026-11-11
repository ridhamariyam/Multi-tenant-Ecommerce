import { download, request } from "./client";

export type ReportName =
  | "sales"
  | "sales-by-product"
  | "sales-by-category"
  | "sales-by-location"
  | "inventory"
  | "unsold"
  | "customers"
  | "coupons"
  | "returns"
  | "analytics";

export const getReport = <T,>(name: ReportName, query: object) =>
  request<T>(`/admin/reports/${name}`, { query });
export type ExportFormat = "csv" | "xlsx" | "pdf";
export const EXPORT_FORMATS: { format: ExportFormat; label: string }[] = [
  { format: "xlsx", label: "Excel" },
  { format: "pdf", label: "PDF" },
  { format: "csv", label: "CSV" },
];

export const downloadReport = (name: ReportName, query: object, format: ExportFormat = "csv") =>
  download(`/admin/reports/${name}`, { ...query, format }, `${name}.${format}`);
