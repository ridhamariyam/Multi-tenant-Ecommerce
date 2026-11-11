import { wishlistApi } from '@/lib/api/cart';
import { ApiError } from '@/lib/api/errors';
import { getAccessToken } from '@/lib/auth/session';
import type { Wishlist } from '@/types/cart';

export const EMPTY_WISHLIST: Wishlist = { id: 'guest', items: [], item_count: 0 };

/**
 * The wishlist as the page should show it.
 *
 * Unlike the cart, there is no guest wishlist -- the backend requires a
 * signed-in customer -- so a visitor without a session simply sees an empty
 * one rather than something assembled client-side.
 */
export async function getWishlist(): Promise<Wishlist> {
  const token = await getAccessToken();
  if (!token) return EMPTY_WISHLIST;

  try {
    return await wishlistApi.get(token);
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthenticated) return EMPTY_WISHLIST;
    throw error;
  }
}
