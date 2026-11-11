export interface MerchantAccount {
  id: string;
  email: string;
  name: string | null;
  phone: string | null;
  status: string;
  is_platform_admin: boolean;
  created_at: string;
}

export interface MerchantSession {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  account: MerchantAccount;
}

export interface Brand {
  id: string;
  name: string;
  slug: string;
  description: string | null;
  logo_url: string | null;
  contact_email: string | null;
  phone: string | null;
  currency: string;
  status: string;
  owner_account_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface Store {
  id: string;
  name: string;
  subdomain: string;
  url: string;
  theme: string;
  logo_url: string | null;
  favicon_url: string | null;
  primary_color: string | null;
  secondary_color: string | null;
  published: boolean;
  published_at: string | null;
}

export interface BrandMembership {
  membership_id: string;
  role: string;
  brand: Brand;
  store: Store | null;
}

export interface BrandToken {
  access_token: string;
  expires_in: number;
  brand_id: string;
  membership_id: string;
}

export interface BrandRegistered {
  brand: Brand;
  store: Store;
  token: BrandToken;
}

export interface Member {
  id: string;
  account_id: string;
  email: string;
  name: string | null;
  role: string;
  status: string;
  created_at: string;
}

export interface StoreDomain {
  id: string;
  domain: string;
  is_primary: boolean;
  verified_at: string | null;
  verification_record: string | null;
  created_at: string;
}

export type StoreUpdate = Partial<
  Pick<Store, "name" | "subdomain" | "theme" | "logo_url" | "favicon_url" | "primary_color" | "secondary_color">
>;

export type AssignableRole = "ADMIN" | "PRODUCT_MANAGER" | "ORDER_MANAGER";

export interface DomainCheck {
  domain: StoreDomain;
  verified: boolean;
  record_name: string;
  expected: string;
  found: string[];
  problem: string | null;
}

export interface PlatformBrand {
  brand: Brand;
  store: Store | null;
  member_count: number;
  suspended_at: string | null;
  suspension_reason: string | null;
}

export interface PlatformDomain {
  domain: StoreDomain;
  brand_id: string;
  brand_name: string;
  store_subdomain: string | null;
}

export interface PlatformOverview {
  brands_total: number;
  brands_active: number;
  brands_suspended: number;
  stores_published: number;
  domains_pending: number;
  merchant_accounts: number;
}
