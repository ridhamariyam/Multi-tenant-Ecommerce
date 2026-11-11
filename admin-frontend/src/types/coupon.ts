export type DiscountType = "FIXED_AMOUNT" | "PERCENTAGE" | "FREE_SHIPPING" | "BOGO";
export const DISCOUNT_TYPES: DiscountType[] = ["PERCENTAGE", "FIXED_AMOUNT", "FREE_SHIPPING", "BOGO"];

export interface Coupon {
  id: string;
  code: string;
  discount_type: DiscountType;
  discount_value: string;
  currency: string;
  min_order_amount: string | null;
  max_discount_amount: string | null;
  starts_at: string | null;
  expires_at: string | null;
  usage_limit: number | null;
  per_customer_usage_limit: number | null;
  times_used: number;
  is_active: boolean;
  is_automatic: boolean;
  first_order_only: boolean;
  min_quantity: number | null;
  buy_quantity: number | null;
  get_quantity: number | null;
  category_ids: string[];
  valid_weekdays: number[];
  created_at: string;
}

// 0 = Monday ... 6 = Sunday, as the backend stores them.
export const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export interface CouponInput {
  code?: string;
  discount_type: DiscountType;
  discount_value: string | null;
  min_order_amount: string | null;
  max_discount_amount: string | null;
  starts_at: string | null;
  expires_at: string | null;
  usage_limit: number | null;
  per_customer_usage_limit: number | null;
  is_active: boolean;
  is_automatic: boolean;
  first_order_only: boolean;
  min_quantity: number | null;
  buy_quantity: number | null;
  get_quantity: number | null;
  category_ids: string[];
  valid_weekdays: number[];
}
