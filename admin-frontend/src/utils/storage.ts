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
