// Keeps the admin session (access + refresh token) so a page refresh doesn't log you out.

const ACCESS_KEY = "cliq_admin_access_token";
const REFRESH_KEY = "cliq_admin_refresh_token";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    // Storage unavailable (e.g. private mode) -- the session just won't survive a refresh.
  }
}

export const getToken = () => read(ACCESS_KEY);
export const getRefreshToken = () => read(REFRESH_KEY);

export function saveTokens(access: string, refresh: string | null): void {
  write(ACCESS_KEY, access);
  if (refresh !== null) write(REFRESH_KEY, refresh);
}

export function clearToken(): void {
  write(ACCESS_KEY, null);
  write(REFRESH_KEY, null);
}

// Merchant mode: a platform session (one login for all of a merchant's brands)
// plus the brand currently open. The brand's own short-lived token is kept in
// the access slot above with no refresh token; it is renewed from the platform
// session (see api/client.ts).
const PLATFORM_ACCESS_KEY = "cliq_platform_access_token";
const PLATFORM_REFRESH_KEY = "cliq_platform_refresh_token";
const BRAND_KEY = "cliq_admin_brand_id";

export const getPlatformToken = () => read(PLATFORM_ACCESS_KEY);
export const getPlatformRefreshToken = () => read(PLATFORM_REFRESH_KEY);
export const getBrandId = () => read(BRAND_KEY);

export function savePlatformTokens(access: string, refresh: string): void {
  write(PLATFORM_ACCESS_KEY, access);
  write(PLATFORM_REFRESH_KEY, refresh);
}

export function setBrandId(brandId: string | null): void {
  write(BRAND_KEY, brandId);
}

/** Leave the open brand: its token and id go, the platform session stays. */
export function clearBrandSession(): void {
  write(ACCESS_KEY, null);
  write(REFRESH_KEY, null);
  write(BRAND_KEY, null);
}

export function clearAllSessions(): void {
  clearBrandSession();
  write(PLATFORM_ACCESS_KEY, null);
  write(PLATFORM_REFRESH_KEY, null);
}
