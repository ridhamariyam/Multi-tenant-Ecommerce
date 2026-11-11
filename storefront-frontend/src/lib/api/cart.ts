import { apiRequest } from '@/lib/api/client';
import type { Cart, Wishlist } from '@/types/cart';

/**
 * Cart and wishlist both require a signed-in customer -- the backend has no
 * guest cart. Every cart mutation answers with the whole cart, so callers
 * should replace their state with the result rather than patching it.
 */
export const cartApi = {
  get(token: string): Promise<Cart> {
    return apiRequest<Cart>('/cart', { token, cache: 'no-store' });
  },

  /** Add a variant. Options must already be resolved to one. */
  addItem(token: string, variantId: string, quantity = 1): Promise<Cart> {
    return apiRequest<Cart>('/cart/items', {
      method: 'POST',
      body: { variant_id: variantId, quantity },
      token,
      cache: 'no-store',
    });
  },

  /** Set a line's quantity. The minimum is 1; removing needs removeItem. */
  updateItem(token: string, itemId: string, quantity: number): Promise<Cart> {
    return apiRequest<Cart>(`/cart/items/${itemId}`, {
      method: 'PATCH',
      body: { quantity },
      token,
      cache: 'no-store',
    });
  },

  removeItem(token: string, itemId: string): Promise<Cart> {
    return apiRequest<Cart>(`/cart/items/${itemId}`, {
      method: 'DELETE',
      token,
      cache: 'no-store',
    });
  },

  clear(token: string): Promise<Cart> {
    return apiRequest<Cart>('/cart', { method: 'DELETE', token, cache: 'no-store' });
  },
};

export const wishlistApi = {
  get(token: string): Promise<Wishlist> {
    return apiRequest<Wishlist>('/wishlist', { token, cache: 'no-store' });
  },

  /** Wishlists hold variants, not products. */
  addItem(token: string, variantId: string): Promise<Wishlist> {
    return apiRequest<Wishlist>('/wishlist/items', {
      method: 'POST',
      body: { variant_id: variantId },
      token,
      cache: 'no-store',
    });
  },

  /** Takes the wishlist item's id, not the variant's. */
  removeItem(token: string, itemId: string): Promise<Wishlist> {
    return apiRequest<Wishlist>(`/wishlist/items/${itemId}`, {
      method: 'DELETE',
      token,
      cache: 'no-store',
    });
  },

  clear(token: string): Promise<Wishlist> {
    return apiRequest<Wishlist>('/wishlist', { method: 'DELETE', token, cache: 'no-store' });
  },
};
