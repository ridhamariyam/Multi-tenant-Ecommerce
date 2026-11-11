import { apiRequest } from '@/lib/api/client';
import type { Cart, Wishlist } from '@/types/cart';

/**
 * The signed-in customer's cart and wishlist. Every cart mutation answers with the whole cart, so callers
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

/**
 * The backend's guest cart, used only to check a guest out: the storefront
 * keeps a guest's cart in its own cookie and copies it here at checkout,
 * because guest checkout prices and orders whatever this cart holds.
 */
const CART_TOKEN_HEADER = 'X-Cart-Token';

export const guestCartApi = {
  /** Answers with `guest_token`, the only time it is returned. */
  create(): Promise<Cart & { guest_token?: string | null }> {
    return apiRequest<Cart & { guest_token?: string | null }>('/cart/guest', { method: 'POST', cache: 'no-store' });
  },

  get(cartToken: string): Promise<Cart> {
    return apiRequest<Cart>('/cart', { headers: { [CART_TOKEN_HEADER]: cartToken }, cache: 'no-store' });
  },

  addItem(cartToken: string, variantId: string, quantity: number): Promise<Cart> {
    return apiRequest<Cart>('/cart/items', {
      method: 'POST',
      body: { variant_id: variantId, quantity },
      headers: { [CART_TOKEN_HEADER]: cartToken },
      cache: 'no-store',
    });
  },

  clear(cartToken: string): Promise<Cart> {
    return apiRequest<Cart>('/cart', { method: 'DELETE', headers: { [CART_TOKEN_HEADER]: cartToken }, cache: 'no-store' });
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
