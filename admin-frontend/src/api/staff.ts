import type { PermissionInfo, StaffMember } from "../types/user";
import { request } from "./client";

export const listStaff = (query: object = {}) => request<StaffMember[]>("/admin/staff", { query });
export const listPermissions = () => request<PermissionInfo[]>("/admin/staff/permissions");
export const createStaff = (data: object) => request<StaffMember>("/admin/staff", { method: "POST", body: data });
export const updateStaff = (id: string, data: object) =>
  request<StaffMember>(`/admin/staff/${id}`, { method: "PATCH", body: data });
export const resetStaffPassword = (id: string, password: string) =>
  request<StaffMember>(`/admin/staff/${id}/password`, { method: "POST", body: { password } });
