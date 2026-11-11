import { cookies } from 'next/headers';

import { authApi } from '@/lib/api/auth';
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_MAX_AGE_SECONDS,
  REFRESH_TOKEN_COOKIE,
  accessCookieOptions,
  isTokenExpired,
  sessionCookieOptions,
} from '@/lib/auth/cookies';
import type { TokenPair } from '@/types/auth';

/**
 * Tokens are held in httpOnly cookies rather than localStorage.
 *
 * The backend hands them back in the response body, so something has to
 * store them. Cookies are the only store middleware and server components
 * can both read, which is what lets a route be refused before it renders
 * and lets pages fetch their own data. httpOnly keeps them away from any
 * script on the page.
 */

/**
 * The access token to authenticate this request with, or null.
 *
 * An expired token reads as no token at all. Handing one out would only
 * produce a 401 the caller has no way to recover from, since a server
 * component cannot write the rotated pair back -- rotation belongs to
 * middleware, which has already had its turn before this runs.
 */
export async function getAccessToken(): Promise<string | null> {
  const store = await cookies();
  const token = store.get(ACCESS_TOKEN_COOKIE)?.value ?? null;

  return isTokenExpired(token) ? null : token;
}

export async function getRefreshToken(): Promise<string | null> {
  const store = await cookies();
  return store.get(REFRESH_TOKEN_COOKIE)?.value ?? null;
}

/**
 * Persist a token pair.
 *
 * Only callable from a server action or route handler -- Next forbids
 * writing cookies while rendering, which is why refresh runs in middleware.
 */
export async function setSession(tokens: TokenPair): Promise<void> {
  const store = await cookies();

  store.set(ACCESS_TOKEN_COOKIE, tokens.access_token, accessCookieOptions());
  store.set(
    REFRESH_TOKEN_COOKIE,
    tokens.refresh_token,
    sessionCookieOptions(REFRESH_MAX_AGE_SECONDS),
  );
}

export async function clearSession(): Promise<void> {
  const store = await cookies();

  store.delete(ACCESS_TOKEN_COOKIE);
  store.delete(REFRESH_TOKEN_COOKIE);
}

/**
 * Rotate the pair and return a usable access token, or null.
 *
 * For server actions, which unlike a render may write cookies. A refresh
 * token is single-use and replaying a spent one revokes every session the
 * customer has, so this must only ever be called where the pair it gets
 * back can actually be stored -- never from a component being rendered.
 */
export async function refreshSession(): Promise<string | null> {
  const refreshToken = await getRefreshToken();
  if (!refreshToken) return null;

  try {
    const tokens = await authApi.refresh(refreshToken);
    await setSession(tokens);
    return tokens.access_token;
  } catch {
    await clearSession();
    return null;
  }
}

/**
 * The access token for a server action, rotating first if it has expired.
 *
 * Pages get their fresh token from middleware, but an action fires from a
 * tab that may have sat open since long after that ran, so it asks here
 * instead of sending a token that is certain to be refused.
 */
export async function getActionAccessToken(): Promise<string | null> {
  return (await getAccessToken()) ?? (await refreshSession());
}

export { ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE };
