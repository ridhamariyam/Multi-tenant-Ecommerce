/**
 * Cookie names and options, kept free of next/headers so middleware can
 * share them. Middleware reads and writes cookies through the request and
 * response objects, which is a different API from the one server actions
 * use, but the names and options have to match.
 */

export const ACCESS_TOKEN_COOKIE = 'cliq_access_token';
export const REFRESH_TOKEN_COOKIE = 'cliq_refresh_token';

/**
 * A little under the backend's REFRESH_TOKEN_EXPIRE_DAYS of 14, so the
 * browser drops an expired cookie rather than sending one that is certain
 * to be rejected.
 */
export const REFRESH_MAX_AGE_SECONDS = 13 * 24 * 60 * 60;

/**
 * Rotate this long before the access token's own expiry.
 *
 * Covers the gap between middleware deciding the token is good and the
 * render behind it finishing its API calls, plus any clock difference
 * between this server and the API's.
 */
export const ACCESS_REFRESH_SKEW_SECONDS = 60;

export function sessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: 'lax' as const,
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge,
  };
}

/**
 * Both cookies outlive the access token deliberately.
 *
 * Giving the access cookie the token's own lifetime made its presence and
 * the token's validity two different facts: the cookie's max-age is counted
 * from the browser's clock when the response lands, the token's `exp` from
 * the API's clock when it was signed, so latency or a skewed clock leaves a
 * window where the cookie is still sent but the token inside it is dead.
 * Nothing rotated in that window -- the cookie was there -- and every call
 * behind it came back 401, which read as a signed-out visitor. Expiry is now
 * decided by `exp` alone, in `isTokenExpired` below.
 */
export function accessCookieOptions() {
  return sessionCookieOptions(REFRESH_MAX_AGE_SECONDS);
}

/**
 * Whether a JWT is past its expiry, give or take `skewSeconds`.
 *
 * The claims are read without verifying the signature, which this side holds
 * no key for. That is safe because the answer only decides when to ask the
 * API for a new pair: a tampered token still has to survive the API's own
 * check, and one that cannot be parsed is treated as expired rather than
 * trusted.
 */
export function isTokenExpired(
  token: string | null | undefined,
  skewSeconds = ACCESS_REFRESH_SKEW_SECONDS,
): boolean {
  if (!token) return true;

  const payload = token.split('.')[1];
  if (!payload) return true;

  try {
    const json = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
    const { exp } = JSON.parse(json) as { exp?: unknown };
    if (typeof exp !== 'number') return true;

    return exp * 1000 <= Date.now() + skewSeconds * 1000;
  } catch {
    return true;
  }
}
