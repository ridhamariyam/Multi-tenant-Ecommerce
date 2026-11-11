import { cache } from 'react';

import { authApi } from '@/lib/api/auth';
import { ApiError } from '@/lib/api/errors';
import { getAccessToken } from '@/lib/auth/session';
import type { UserProfile } from '@/types/auth';

/**
 * The signed-in user for this request, or null for a guest.
 *
 * Cached for the lifetime of one request so a layout and the page inside it
 * do not each call /auth/me. An expired or rejected token reads as a guest
 * rather than an error: middleware has already had its chance to refresh,
 * so a 401 here means the visitor really is signed out.
 */
export const getCurrentUser = cache(async (): Promise<UserProfile | null> => {
  const token = await getAccessToken();
  if (!token) return null;

  try {
    return await authApi.me(token);
  } catch (error) {
    if (error instanceof ApiError && (error.isUnauthenticated || error.isForbidden)) {
      return null;
    }
    throw error;
  }
});
