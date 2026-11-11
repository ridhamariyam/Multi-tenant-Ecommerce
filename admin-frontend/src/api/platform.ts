import type {
  AssignableRole,
  BrandMembership,
  BrandRegistered,
  BrandToken,
  Member,
  MerchantAccount,
  MerchantSession,
  Store,
  StoreDomain,
  StoreUpdate,
} from "../types/platform";
import { request } from "./client";

// Merchant account (one login for every brand the person belongs to).
export const registerMerchant = (body: { name: string; email: string; password: string; phone?: string | null }) =>
  request<MerchantSession>("/platform/auth/register", { method: "POST", body, auth: false });
export const loginMerchant = (email: string, password: string) =>
  request<MerchantSession>("/platform/auth/login", { method: "POST", body: { email, password }, auth: false });
export const logoutMerchant = (refreshToken: string) =>
  request<null>("/platform/auth/logout", { method: "POST", body: { refresh_token: refreshToken }, auth: false });
export const getMerchant = () => request<MerchantAccount>("/platform/auth/me", { session: "platform" });

// Brands: list, create, open.
export const listMyBrands = () => request<BrandMembership[]>("/brands/me", { session: "platform" });
export const registerBrand = (body: { name: string; subdomain?: string; description?: string | null }) =>
  request<BrandRegistered>("/brands/register", { method: "POST", body, session: "platform" });
export const switchBrand = (brandId: string) =>
  request<BrandToken>(`/brands/${encodeURIComponent(brandId)}/switch`, { method: "POST", session: "platform" });

// Team (platform session; the API checks the caller is the brand's owner or admin).
export const listMembers = (brandId: string) =>
  request<Member[]>(`/brands/${encodeURIComponent(brandId)}/members`, { session: "platform" });
export const addMember = (brandId: string, email: string, role: AssignableRole) =>
  request<Member>(`/brands/${encodeURIComponent(brandId)}/members`, { method: "POST", body: { email, role }, session: "platform" });
export const updateMember = (brandId: string, memberId: string, body: { role?: AssignableRole; status?: "ACTIVE" | "REMOVED" }) =>
  request<Member>(`/brands/${encodeURIComponent(brandId)}/members/${encodeURIComponent(memberId)}`, {
    method: "PATCH",
    body,
    session: "platform",
  });

// The open brand's store (brand token).
export const getStore = () => request<Store>("/brand/store");
export const updateStore = (body: StoreUpdate) => request<Store>("/brand/store", { method: "PUT", body });
export const publishStore = (published: boolean) =>
  request<Store>("/brand/store/publish", { method: "POST", body: { published } });
export const listDomains = () => request<StoreDomain[]>("/brand/domains");
export const addDomain = (domain: string, isPrimary = false) =>
  request<StoreDomain>("/brand/domains", { method: "POST", body: { domain, is_primary: isPrimary } });
export const removeDomain = (domainId: string) =>
  request<null>(`/brand/domains/${encodeURIComponent(domainId)}`, { method: "DELETE" });
