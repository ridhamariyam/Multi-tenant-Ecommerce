'use server';

import { revalidatePath } from 'next/cache';

import { catalogueApi } from '@/lib/api/catalogue';
import { wishlistApi } from '@/lib/api/cart';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { getActionAccessToken } from '@/lib/auth/session';
import { getWishlist } from '@/lib/wishlist/read';
import type { Wishlist } from '@/types/cart';

export interface WishlistMutation {
  wishlist: Wishlist;
  error: string | null;
}

function toMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.isRateLimited) return 'Too many requests. Try again shortly.';
    return error.message;
  }

  if (error instanceof ApiUnreachableError) return 'Could not reach CliQ. Try again in a moment.';

  throw error;
}

/**
 * Mutations the wishlist provider calls directly.
 *
 * Each answers with the whole wishlist, mirroring the cart provider, so the
 * client always renders the backend's own state rather than a local guess.
 */
async function mutate(apply: (token: string) => Promise<Wishlist>): Promise<WishlistMutation> {
  const token = await getActionAccessToken();
  if (!token) {
    return { wishlist: await getWishlist(), error: 'Sign in to save pieces to your wishlist.' };
  }

  try {
    const wishlist = await apply(token);
    revalidatePath('/wishlist');
    return { wishlist, error: null };
  } catch (error) {
    return { wishlist: await getWishlist(), error: toMessage(error) };
  }
}

/** Save a specific variant -- used where one is already chosen, like the product page. */
export async function addWishlistVariant(variantId: string): Promise<WishlistMutation> {
  return mutate(token => wishlistApi.addItem(token, variantId));
}

export async function removeWishlistItem(itemId: string): Promise<WishlistMutation> {
  return mutate(token => wishlistApi.removeItem(token, itemId));
}

/**
 * Toggle a product's saved state from a listing card, which knows no variant.
 *
 * Resolves the same default the product page starts on -- the first
 * in-stock variant, or else the first of any -- so saving a single-variant
 * product (most of them) from its card matches opening the page and saving
 * it there.
 */
export async function toggleWishlistByProduct(productId: string): Promise<WishlistMutation> {
  const token = await getActionAccessToken();
  if (!token) {
    return { wishlist: await getWishlist(), error: 'Sign in to save pieces to your wishlist.' };
  }

  try {
    const current = await wishlistApi.get(token);
    const existing = current.items.find(item => item.product_id === productId);

    if (existing) {
      const wishlist = await wishlistApi.removeItem(token, existing.id);
      revalidatePath('/wishlist');
      return { wishlist, error: null };
    }

    const product = await catalogueApi.getProduct(productId);
    const variant = product.variants.find(entry => entry.in_stock) ?? product.variants[0];
    if (!variant) return { wishlist: current, error: 'This product has no option to save.' };

    const wishlist = await wishlistApi.addItem(token, variant.id);
    revalidatePath('/wishlist');
    return { wishlist, error: null };
  } catch (error) {
    return { wishlist: await getWishlist(), error: toMessage(error) };
  }
}
