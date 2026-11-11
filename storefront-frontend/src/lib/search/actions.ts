'use server';

import { searchApi } from '@/lib/api/search';
import { getActionAccessToken } from '@/lib/auth/session';

/** The signed-in shopper's recent searches, newest first. Empty for a guest. */
export async function getSearchHistory(): Promise<string[]> {
  const token = await getActionAccessToken();
  if (!token) return [];

  try {
    return await searchApi.history(token);
  } catch {
    return [];
  }
}
