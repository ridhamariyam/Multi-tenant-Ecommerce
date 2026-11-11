import type { Integration, OrderSheetSettings, OrderSheetSettingsInput, OrderSheetSyncResult } from "../types/settings";
import { request } from "./client";

export const listIntegrations = () => request<Integration[]>("/admin/integrations");

export const getOrderSheet = () => request<OrderSheetSettings>("/admin/integrations/google-sheets");
export const saveOrderSheet = (body: OrderSheetSettingsInput) =>
  request<OrderSheetSettings>("/admin/integrations/google-sheets", { method: "PUT", body });
export const syncOrderSheet = () =>
  request<OrderSheetSyncResult>("/admin/integrations/google-sheets/sync", { method: "POST" });
