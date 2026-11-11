'use server';

import { redirect } from 'next/navigation';

import { authApi } from '@/lib/api/auth';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import type { AuthFormState } from '@/lib/auth/form-state';
import {
  clearSession,
  getActionAccessToken,
  getRefreshToken,
  setSession,
} from '@/lib/auth/session';
import { mergeGuestCart } from '@/lib/cart/actions';

/**
 * Turn a failed call into something a form can show.
 *
 * Rate limiting and unreachability get their own wording because the
 * remedy differs -- one is "wait", the other is "the server is down".
 */
function toFormState(error: unknown): AuthFormState {
  if (error instanceof ApiError) {
    if (error.isRateLimited) {
      const wait = error.retryAfterSeconds;
      return {
        error: wait
          ? `Too many attempts. Try again in ${wait} seconds.`
          : 'Too many attempts. Try again shortly.',
      };
    }

    return { error: error.message, fieldErrors: error.fieldErrors() };
  }

  if (error instanceof ApiUnreachableError) {
    return { error: 'Could not reach CliQ. Check your connection and try again.' };
  }

  throw error;
}

/**
 * Turn a verified MSG91 widget token into a session.
 *
 * The code itself never reaches this server. MSG91's widget collects the
 * number, sends the SMS and checks the digits in the browser, then hands
 * back an access token; the backend confirms that token with MSG91 and
 * reads the number from its answer. Registration happens here too -- a
 * verified number with no account gets one.
 */
export async function signInWithWidgetToken(
  accessToken: string,
  next: string,
): Promise<AuthFormState> {
  if (!accessToken) return { error: 'Verification failed. Start again.' };

  try {
    const tokens = await authApi.widgetLogin(accessToken);
    await setSession(tokens);

    // Anything gathered while signed out moves into the real cart now, so
    // the shopper does not lose what they picked before signing in.
    await mergeGuestCart(tokens.access_token);
  } catch (error) {
    return toFormState(error);
  }

  redirect(safeRedirect(next));
}

export async function signInWithGoogleCredential(
  credential: string,
  next: string,
): Promise<AuthFormState> {
  if (!credential) return { error: 'Google sign-in failed. Try again.' };

  try {
    const tokens = await authApi.googleLogin(credential);
    await setSession(tokens);
    await mergeGuestCart(tokens.access_token);
  } catch (error) {
    return toFormState(error);
  }

  redirect(safeRedirect(next));
}

/** End the session, revoking the refresh token server-side as well. */
export async function logout(): Promise<void> {
  const refreshToken = await getRefreshToken();

  if (refreshToken) {
    try {
      await authApi.logout(refreshToken);
    } catch {
      // The cookies still get cleared: a revoke that fails must not strand
      // someone in a session they have asked to leave.
    }
  }

  await clearSession();
  redirect('/');
}

/**
 * Erase the account. Past orders survive, stripped of the person.
 *
 * The session is cleared either way: a failed erase must not strand someone
 * signed in to an account they just asked to leave.
 */
export async function deleteAccount(): Promise<void> {
  const token = await getActionAccessToken();

  if (token) {
    try {
      await authApi.deleteAccount(token);
    } catch {
      // See above -- the cookies still get cleared.
    }
  }

  await clearSession();
  redirect('/');
}

/**
 * Only allow redirects to a path on this site.
 *
 * `next` arrives from the query string, so without this an attacker could
 * link to a sign-in that lands on their own domain afterwards.
 */
function safeRedirect(target: string): string {
  if (!target.startsWith('/') || target.startsWith('//')) return '/';
  return target;
}

/** Turn marketing email on or off for the signed-in customer. */
export async function setMarketingConsent(optIn: boolean, email?: string | null): Promise<{ ok: boolean; message: string | null }> {
  const token = await getActionAccessToken();
  if (!token) return { ok: false, message: 'Sign in again to change this.' };
  try {
    await authApi.updateMe(token, email ? { marketing_opt_in: optIn, email } : { marketing_opt_in: optIn });
    return { ok: true, message: null };
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : 'Could not save.' };
  }
}
