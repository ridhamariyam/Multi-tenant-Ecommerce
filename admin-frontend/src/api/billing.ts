import { request } from "./client";

export interface Plan {
  code: string;
  name: string;
  monthly_price: number; // paise, before GST
  monthly_price_with_gst: number; // paise, what is charged
  currency: string;
  monthly_ai_credits: number;
  product_limit: number | null;
  staff_limit: number | null;
  features: Record<string, boolean>;
  is_active: boolean;
}

export interface Billing {
  plan: Plan | null;
  effective_plan: Plan | null;
  subscription: {
    status: "TRIALING" | "ACTIVE" | "PAST_DUE" | "CANCELLED";
    billing_provider: string;
    current_period_start: string;
    current_period_end: string;
    cancel_at_period_end: boolean;
    trial_used: boolean;
    lapsed: boolean;
  } | null;
  usage: { products: number; staff: number };
  plans: Plan[];
  online_billing: boolean;
  /** The storefront is closed to shoppers until the brand pays. */
  paused: boolean;
  trial_ends_at: string | null;
  trial_days_left: number | null;
  gst_percent: number;
}

export interface BillingCheckout {
  subscription_id: string;
  key_id: string;
  plan_code: string;
  plan_name: string;
  amount: number; // incl. GST
  amount_before_gst: number;
  currency: string;
  trial_days: number;
  first_charge_at: string | null;
}

export const getBilling = () => request<Billing>("/brand/billing");
export const startCheckout = (planCode: string) =>
  request<BillingCheckout>("/brand/billing/checkout", { method: "POST", body: { plan_code: planCode } });
export const confirmCheckout = (body: { razorpay_payment_id: string; razorpay_subscription_id: string; razorpay_signature: string }) =>
  request<Billing>("/brand/billing/confirm", { method: "POST", body });
export const cancelSubscription = () => request<Billing>("/brand/billing/cancel", { method: "POST" });

// Platform operators.
export const listPlans = () => request<Plan[]>("/platform/admin/plans", { session: "platform" });
export const savePlan = (code: string, body: Omit<Plan, "code" | "currency" | "monthly_price_with_gst">) =>
  request<Plan>(`/platform/admin/plans/${encodeURIComponent(code)}`, { method: "PUT", body, session: "platform" });
export const assignPlan = (brandId: string, planCode: string) =>
  request<Plan>(`/platform/admin/brands/${encodeURIComponent(brandId)}/plan`, { method: "PUT", body: { plan_code: planCode }, session: "platform" });
