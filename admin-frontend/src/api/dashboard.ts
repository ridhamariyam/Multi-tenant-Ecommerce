import type { DashboardOverview } from "../types/dashboard";
import { request } from "./client";

export const getDashboardOverview = () => request<DashboardOverview>("/admin/dashboard");
