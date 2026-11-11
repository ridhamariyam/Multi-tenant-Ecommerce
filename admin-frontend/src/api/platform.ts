import type {
  AssignableRole,
  DomainCheck,
  PlatformBrand,
  PlatformDomain,
  PlatformOverview,
  SystemHealth,
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
export const checkDomain = (domainId: string) =>
  request<DomainCheck>(`/brand/domains/${encodeURIComponent(domainId)}/check`, { method: "POST" });

// CliQ. platform operators (merchant accounts with is_platform_admin).
export const platformOverview = () => request<PlatformOverview>("/platform/admin/overview", { session: "platform" });
export const platformBrands = (query: { page?: number; page_size?: number; search?: string; status?: string }) =>
  request<PlatformBrand[]>("/platform/admin/brands", { query, session: "platform" });
export const suspendBrand = (brandId: string, reason: string) =>
  request<PlatformBrand>(`/platform/admin/brands/${encodeURIComponent(brandId)}/suspend`, {
    method: "POST",
    body: { reason },
    session: "platform",
  });
export const reinstateBrand = (brandId: string) =>
  request<PlatformBrand>(`/platform/admin/brands/${encodeURIComponent(brandId)}/activate`, { method: "POST", session: "platform" });
export const platformDomains = (query: { page?: number; page_size?: number; status?: string; search?: string }) =>
  request<PlatformDomain[]>("/platform/admin/domains", { query, session: "platform" });
export const platformCheckDomain = (domainId: string) =>
  request<DomainCheck>(`/platform/admin/domains/${encodeURIComponent(domainId)}/check`, { method: "POST", session: "platform" });
export const platformVerifyDomain = (domainId: string) =>
  request<StoreDomain>(`/platform/admin/domains/${encodeURIComponent(domainId)}/verify`, { method: "POST", session: "platform" });
export const platformSystem = () => request<SystemHealth>("/platform/admin/system", { session: "platform" });
