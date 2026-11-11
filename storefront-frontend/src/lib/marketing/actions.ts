'use server';

import { apiRequest } from '@/lib/api/client';
import { ApiError } from '@/lib/api/errors';

export async function unsubscribeFromMarketing(userId: string, token: string): Promise<{ ok: boolean; message: string | null }> {
  try {
    await apiRequest('/storefront/unsubscribe', { method: 'POST', body: { u: userId, t: token }, cache: 'no-store' });
    return { ok: true, message: null };
  } catch (error) {
    return { ok: false, message: error instanceof ApiError ? error.message : 'Could not reach the store. Try again.' };
  }
}
