export interface ShippingSettings {
  shipping_amount: string;
  free_shipping_minimum: string | null;
  is_active: boolean;
  min_delivery_days: number;
  max_delivery_days: number;
  restrict_to_listed_pincodes: boolean;
}

export interface TaxSettings {
  tax_percentage: string;
  is_active: boolean;
  confirmed_by_ca: boolean;
}

export interface PincodeRule {
  pincode: string;
  is_serviceable: boolean;
  cod_available: boolean;
  min_delivery_days: number | null;
  max_delivery_days: number | null;
  shipping_amount: string | null;
  city: string | null;
  state: string | null;
}

export interface GstSettings {
  gstin: string | null;
  legal_name: string | null;
  address: string | null;
  state: string | null;
  state_code: string | null;
  invoice_prefix: string;
  shipping_sac_code: string | null;
  registration_status: "REGISTERED" | "NOT_REGISTERED" | "APPLICATION_PENDING" | "UNKNOWN";
  accounting_software: "TALLY" | "ZOHO_BOOKS" | "OTHER" | "NONE" | "NOT_DECIDED";
  configuration_status: "DRAFT" | "PENDING_CA_CONFIRMATION" | "ACTIVE";
  prices_include_gst: boolean;
  gst_enabled: boolean;
  default_classification: "APPAREL" | null;
  fallback_gst_rate: string | null;
  defaults_reviewed_at: string | null;
  defaults_reviewed_by_id: string | null;
  is_system_default?: boolean;
  updated_at: string | null;
  updated_by_id: string | null;
  confirmed_at: string | null;
  confirmed_by_id: string | null;
}

export interface TaxRateConfiguration {
  id: string;
  product_id: string | null;
  category_id: string | null;
  product_name?: string | null;
  category_name?: string | null;
  hsn_code: string;
  gst_rate: string;
  effective_from: string;
  status: "PENDING" | "ACTIVE" | "RETIRED";
  ca_confirmed: boolean;
  approved_at: string | null;
  created_by_id?: string | null;
  approved_by_id?: string | null;
  created_at: string;
}

export interface GstDefaultRule {
  id: string;
  code: string;
  classification: string;
  description: string;
  hsn_prefixes: string[];
  min_unit_value: string | null;
  max_unit_value: string | null;
  gst_rate: string;
  effective_from: string;
  effective_to: string | null;
  is_fallback: boolean;
  verification_status: "UNVERIFIED" | "VERIFIED";
  source: string | null;
  in_force: boolean;
}

export interface GstDefaults {
  rules: GstDefaultRule[];
  default_classification: string | null;
  fallback_gst_rate: string | null;
  system_fallback_rate: string | null;
  reviewed_at: string | null;
  reviewed_by_id: string | null;
  status: "AWAITING_VERIFICATION" | "REVIEWED";
}

export type TaxSource = "APPROVED_OVERRIDE" | "MANUAL" | "SYSTEM_DEFAULT" | "FALLBACK" | "DISABLED";
export type TaxVerification = "VERIFIED" | "AWAITING_VERIFICATION" | "NEEDS_REVIEW" | "NOT_APPLICABLE";

export interface ProductTaxReview {
  product_id: string;
  product_name: string;
  category_name: string | null;
  hsn_code: string | null;
  source: TaxSource;
  verification: TaxVerification;
  rule_codes: string[];
  rates: string[];
  reason: string;
  needs_review: boolean;
}

export interface TaxRateTargets {
  products: { id: string; name: string }[];
  categories: { id: string; name: string }[];
}

export interface CodSettings {
  is_enabled: boolean;
  min_order_amount: string | null;
  max_order_amount: string | null;
  fee_amount: string;
  advance_amount: string | null;
  auto_blacklist_threshold: number | null;
}

export interface CodCollection {
  payment_id: string;
  order_id: string;
  order_number: string;
  amount: string;
  collected_at: string;
  remitted_at: string | null;
  remittance_reference: string | null;
}

export interface Integration {
  key: string;
  name: string;
  purpose: string;
  credentials_configured: boolean;
  integrated: boolean;
  status: string;
  required_settings: string[];
  note: string;
}

export interface GstReport {
  start_date: string;
  end_date: string;
  order_count: number;
  taxable_amount: string;
  cgst_amount: string;
  sgst_amount: string;
  igst_amount: string;
  unclassified_tax_amount?: string;
  tax_amount: string;
  // gst_type/gst_rate are null for orders placed before the seller's GST state was set.
  by_rate: { component?: "ITEMS" | "CHARGES_AND_ADJUSTMENTS"; gst_type: "INTRA_STATE" | "INTER_STATE" | null; gst_rate: string | null; hsn_code?: string | null; taxable_amount: string; cgst_amount: string; sgst_amount: string; igst_amount: string }[];
  currency: string;
}
