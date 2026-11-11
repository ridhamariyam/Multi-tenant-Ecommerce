import { NextResponse, type NextRequest } from 'next/server';

import { authApi } from '@/lib/api/auth';
import {
  ACCESS_TOKEN_COOKIE,
  REFRESH_MAX_AGE_SECONDS,
  REFRESH_TOKEN_COOKIE,
  accessCookieOptions,
  isTokenExpired,
  sessionCookieOptions,
} from '@/lib/auth/cookies';
import { SIGN_IN_PARAM } from '@/lib/auth/sign-in-url';
import { LEGACY_ROUTES } from '@/constant/legacyRoutes';

/**
 * Routes that need a signed-in customer.
 *
 * /cart is deliberately absent: guests keep a cookie-backed cart that
 * is merged after sign-in, so they have to be able to see it.
 */
const CUSTOMER_PREFIXES = [
  '/account',
  '/my-account',
  '/check-out',
  '/checkout',
  '/order-confirmation',
  '/my-orders',
  '/order-success',
  '/invoice',
  '/payment-history',
];

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some(prefix => pathname === prefix || pathname.startsWith(`${prefix}/`));
}

/**
 * Refresh the session and guard protected routes.
 *
 * Refresh has to happen here because Next forbids writing cookies while
 * rendering: a server component can read the access token but cannot
 * replace an expired one. Middleware runs before rendering and can set
 * cookies on the response, so it is the only place a rotation can be
 * persisted -- and because the matcher below covers server action posts as
 * well as navigations, every path into the app passes through it.
 *
 * Guarding here is a first gate, not the authority. Every protected call
 * is checked again by the backend against the role on the token, so a
 * bypass of this check still fails at the API.
 */
export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;

  let accessToken = request.cookies.get(ACCESS_TOKEN_COOKIE)?.value ?? null;
  const refreshToken = request.cookies.get(REFRESH_TOKEN_COOKIE)?.value ?? null;

  let refreshed: { access: string; refresh: string } | null = null;
  let refreshFailed = false;

  /* Rotation is driven by the token's own `exp`, not by whether a cookie is
     still around. The two used to be the same test, and they disagree: the
     cookie's lifetime is counted from the browser's clock when the response
     arrives, `exp` from the API's when the token was signed. In the window
     between them the cookie was sent, so nothing rotated, and every call the
     page made came back 401 -- a signed-in customer rendered as a guest,
     with /account bouncing them to sign-in. */
  if (isTokenExpired(accessToken) && refreshToken) {
    try {
      const tokens = await authApi.refresh(refreshToken);
      accessToken = tokens.access_token;
      refreshed = { access: tokens.access_token, refresh: tokens.refresh_token };
    } catch {
      accessToken = null;
      refreshFailed = true;
    }
  } else if (isTokenExpired(accessToken)) {
    accessToken = null;
  }

  let response: NextResponse;

  if (matches(pathname, CUSTOMER_PREFIXES) && !accessToken) {
    const url = request.nextUrl.clone();
    url.pathname = '/';
    url.search = `?${SIGN_IN_PARAM}=1&next=${encodeURIComponent(pathname + search)}`;
    response = NextResponse.redirect(url);
  } else if (refreshed) {
    /* The rotated token has to reach the render, not just the browser: a
       server component reads the cookies that came in with the request, and
       those still carry the expired one. */
    const headers = new Headers(request.headers);
    const jar = request.cookies;
    jar.set(ACCESS_TOKEN_COOKIE, refreshed.access);
    jar.set(REFRESH_TOKEN_COOKIE, refreshed.refresh);
    headers.set('cookie', jar.toString());
    response = NextResponse.next({ request: { headers } });
  } else {
    response = NextResponse.next();
  }

  if (refreshed) {
    response.cookies.set(ACCESS_TOKEN_COOKIE, refreshed.access, accessCookieOptions());
    response.cookies.set(
      REFRESH_TOKEN_COOKIE,
      refreshed.refresh,
      sessionCookieOptions(REFRESH_MAX_AGE_SECONDS),
    );
  }

  // The template's demo pages stay reachable but out of search results.
  if (LEGACY_ROUTES.has(pathname)) response.headers.set('X-Robots-Tag', 'noindex');

  if (refreshFailed) {
    response.cookies.delete(ACCESS_TOKEN_COOKIE);
    response.cookies.delete(REFRESH_TOKEN_COOKIE);
  }

  return response;
}

export const config = {
  matcher: [
    /*
     * Everything except Next's own assets and files with an extension, so
     * the refresh runs on navigations rather than on every image request.
     */
    '/((?!_next/static|_next/image|favicon.ico|assets|.*\\.).*)',
  ],
};
