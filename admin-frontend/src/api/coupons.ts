import type { Coupon, CouponInput } from "../types/coupon";
import { request } from "./client";

export const listCoupons = (query: object) => request<Coupon[]>("/admin/coupons", { query });
export const createCoupon = (data: CouponInput) => request<Coupon>("/admin/coupons", { method: "POST", body: data });
export const updateCoupon = (id: string, data: CouponInput) =>
  request<Coupon>(`/admin/coupons/${id}`, { method: "PUT", body: data });
export const deleteCoupon = (id: string) => request<null>(`/admin/coupons/${id}`, { method: "DELETE" });
