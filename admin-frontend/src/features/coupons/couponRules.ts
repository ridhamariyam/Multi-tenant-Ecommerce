import type { Coupon, CouponInput, DiscountType } from "../../types/coupon";
import { emptyToNull, isoToLocalInput, localInputToIso } from "../../utils/formatters";

export const TYPE_HELP: Record<DiscountType, string> = {
  PERCENTAGE: "Percent off the eligible items",
  FIXED_AMOUNT: "Fixed rupee amount off",
  FREE_SHIPPING: "Removes the shipping charge",
  BOGO: "Buy X, get Y at a percent off (100 = free)",
};

export function toForm(c: Coupon | null) {
  return {
    code: c?.code ?? "",
    discount_type: (c?.discount_type ?? "PERCENTAGE") as DiscountType,
    discount_value: c?.discount_value ?? "",
    min_order_amount: c?.min_order_amount ?? "",
    max_discount_amount: c?.max_discount_amount ?? "",
    starts_at: isoToLocalInput(c?.starts_at ?? null),
    expires_at: isoToLocalInput(c?.expires_at ?? null),
    usage_limit: c?.usage_limit?.toString() ?? "",
    per_customer_usage_limit: c?.per_customer_usage_limit?.toString() ?? "",
    is_active: c?.is_active ?? true,
    is_automatic: c?.is_automatic ?? false,
    first_order_only: c?.first_order_only ?? false,
    min_quantity: c?.min_quantity?.toString() ?? "",
    buy_quantity: c?.buy_quantity?.toString() ?? "",
    get_quantity: c?.get_quantity?.toString() ?? "",
    category_ids: c?.category_ids ?? [],
    valid_weekdays: c?.valid_weekdays ?? [],
  };
}

export type FormState = ReturnType<typeof toForm>;

// Client-side checks mirroring the backend rules, so mistakes show before saving.
export function validateCoupon(f: FormState, isNew: boolean): string | null {
  const errors = couponFieldErrors(f, isNew);
  if (errors.code) return errors.code;
  if (errors.discount_value) return errors.discount_value;
  if (errors.buy_quantity || errors.get_quantity) return "BOGO needs buy and get quantities of at least 1.";
  return Object.values(errors)[0] ?? null;
}

export function couponFieldErrors(f: FormState, isNew: boolean): Record<string, string> {
  const errors: Record<string, string> = {};
  if (isNew && !f.code.trim()) errors.code = "Coupon code is required.";
  else if (isNew && !/^[A-Za-z0-9_-]{1,50}$/.test(f.code.trim())) errors.code = "Code: letters, numbers, - and _ only (max 50).";
  const value = Number(f.discount_value);
  if (f.discount_type !== "FREE_SHIPPING" && !(value > 0)) errors.discount_value = "Enter a discount value greater than 0.";
  else if ((f.discount_type === "PERCENTAGE" || f.discount_type === "BOGO") && value > 100) errors.discount_value = "A percentage cannot exceed 100.";
  if (f.discount_type === "BOGO") {
    if (!Number.isInteger(Number(f.buy_quantity)) || !(Number(f.buy_quantity) >= 1 && Number(f.buy_quantity) <= 100)) errors.buy_quantity = "Buy quantity must be from 1 to 100.";
    if (!Number.isInteger(Number(f.get_quantity)) || !(Number(f.get_quantity) >= 1 && Number(f.get_quantity) <= 100)) errors.get_quantity = "Get quantity must be from 1 to 100.";
  }
  if (f.min_order_amount.trim() && !(Number(f.min_order_amount) >= 0)) errors.min_order_amount = "Minimum order must be 0 or more.";
  if (f.discount_type === "PERCENTAGE" && f.max_discount_amount.trim() && !(Number(f.max_discount_amount) >= 0)) errors.max_discount_amount = "Maximum discount must be 0 or more.";
  if (f.min_quantity.trim() && (!Number.isInteger(Number(f.min_quantity)) || !(Number(f.min_quantity) >= 1 && Number(f.min_quantity) <= 1000))) errors.min_quantity = "Minimum items must be from 1 to 1000.";
  if (f.usage_limit.trim() && (!Number.isInteger(Number(f.usage_limit)) || Number(f.usage_limit) < 0)) errors.usage_limit = "Total uses must be a whole number of 0 or more.";
  if (f.per_customer_usage_limit.trim() && (!Number.isInteger(Number(f.per_customer_usage_limit)) || Number(f.per_customer_usage_limit) < 0)) errors.per_customer_usage_limit = "Uses per customer must be a whole number of 0 or more.";
  if (f.starts_at && Number.isNaN(new Date(f.starts_at).getTime())) errors.starts_at = "Enter a valid start date.";
  if (f.expires_at && Number.isNaN(new Date(f.expires_at).getTime())) errors.expires_at = "Enter a valid end date.";
  if (f.starts_at && f.expires_at && new Date(f.expires_at) <= new Date(f.starts_at)) errors.expires_at = "The end date must be after the start date.";
  return errors;
}

const int = (v: string) => (v.trim() === "" ? null : Number(v));

export function toPayload(f: FormState, isNew: boolean): CouponInput {
  return {
    ...(isNew ? { code: f.code.trim().toUpperCase() } : {}),
    discount_type: f.discount_type,
    discount_value: f.discount_type === "FREE_SHIPPING" ? null : emptyToNull(f.discount_value),
    min_order_amount: emptyToNull(f.min_order_amount),
    max_discount_amount: f.discount_type === "PERCENTAGE" ? emptyToNull(f.max_discount_amount) : null,
    starts_at: localInputToIso(f.starts_at),
    expires_at: localInputToIso(f.expires_at),
    usage_limit: int(f.usage_limit),
    per_customer_usage_limit: int(f.per_customer_usage_limit),
    is_active: f.is_active,
    is_automatic: f.is_automatic,
    first_order_only: f.first_order_only,
    min_quantity: int(f.min_quantity),
    buy_quantity: f.discount_type === "BOGO" ? int(f.buy_quantity) : null,
    get_quantity: f.discount_type === "BOGO" ? int(f.get_quantity) : null,
    category_ids: f.category_ids,
    valid_weekdays: [...f.valid_weekdays].sort((a, b) => a - b),
  };
}
