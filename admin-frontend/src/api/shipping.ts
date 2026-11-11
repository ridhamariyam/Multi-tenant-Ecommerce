import type { PincodeRule, ShippingSettings } from "../types/settings";
import { request } from "./client";

export const getShipping = () => request<ShippingSettings>("/admin/shipping");
export const updateShipping = (data: ShippingSettings) =>
  request<ShippingSettings>("/admin/shipping", { method: "PUT", body: data });
export const listPincodes = (query: object) => request<PincodeRule[]>("/admin/pincodes", { query });
export const savePincode = (pincode: string, data: Omit<PincodeRule, "pincode">) =>
  request<PincodeRule>(`/admin/pincodes/${pincode}`, { method: "PUT", body: data });
export const bulkPincodes = (rules: PincodeRule[]) =>
  request<{ saved: number }>("/admin/pincodes/bulk", { method: "POST", body: { rules } });
export const deletePincode = (pincode: string) =>
  request<null>(`/admin/pincodes/${pincode}`, { method: "DELETE" });
