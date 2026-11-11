import type { Integration } from "../types/settings";
import { request } from "./client";

export const listIntegrations = () => request<Integration[]>("/admin/integrations");
