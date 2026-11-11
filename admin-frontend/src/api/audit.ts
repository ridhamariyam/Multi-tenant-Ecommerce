import type { AuditLog } from "../types/user";
import { request } from "./client";

export const listAuditLogs = (query: object) => request<AuditLog[]>("/admin/audit-logs", { query });
