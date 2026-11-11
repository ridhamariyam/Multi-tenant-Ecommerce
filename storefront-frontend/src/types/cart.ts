export interface CartItemImage {
  url: string;
  alt_text: string | null;
}

export interface CartItem {
  id: string;
  variant_id: string;
  product_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  quantity: number;
  unit_price: string;
  subtotal: string;
  image: CartItemImage | null;
}

/**
 * The whole cart. Every mutation returns it, so it is the single source of
 * truth rather than something to patch locally. Totals beyond `subtotal`
 * come from the checkout preview.
 */
export interface Cart {
  id: string;
  items: CartItem[];
  subtotal: string;
  item_count: number;
}

export interface WishlistItemImage {
  url: string;
  alt_text: string | null;
}

export interface WishlistItem {
  id: string;
  variant_id: string;
  product_id: string;
  product_name: string;
  variant_name: string;
  sku: string;
  unit_price: number;
  image: WishlistItemImage | null;
}

export interface Wishlist {
  id: string;
  items: WishlistItem[];
  item_count: number;
}

export const MAX_ITEM_QUANTITY = 999;
