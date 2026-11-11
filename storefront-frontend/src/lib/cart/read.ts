import { cartApi } from '@/lib/api/cart';
import { catalogueApi } from '@/lib/api/catalogue';
import { ApiError } from '@/lib/api/errors';
import { getAccessToken } from '@/lib/auth/session';
import { readGuestCart } from '@/lib/cart/guest-cart';
import type { Cart, CartItem } from '@/types/cart';

function toPaise(amount: string): number {
  return Math.round(Number(amount) * 100);
}

function fromPaise(paise: number): string {
  return (paise / 100).toFixed(2);
}

const EMPTY_CART: Cart = { id: 'guest', items: [], subtotal: '0.00', item_count: 0 };

export async function getCart(): Promise<Cart> {
  const token = await getAccessToken();

  if (token) {
    try {
      return await cartApi.get(token);
    } catch (error) {
      if (error instanceof ApiError && error.isUnauthenticated) return EMPTY_CART;
      throw error;
    }
  }

  const lines = await readGuestCart();
  if (lines.length === 0) return EMPTY_CART;

  const variants = await Promise.all(
    lines.map(async (line) => {
      try {
        const variant = await catalogueApi.getVariant(line.variant_id);
        const product = await catalogueApi.getProduct(variant.product_id).catch(() => null);
        return { line, variant, product };
      } catch {
        return null;
      }
    }),
  );

  const items: CartItem[] = [];
  // Money is summed in integer paise so float rounding can never drift.
  let subtotalPaise = 0;

  for (const entry of variants) {
    if (!entry) continue;

    const { line, variant, product } = entry;
    const linePaise = toPaise(variant.price) * line.quantity;
    subtotalPaise += linePaise;

    const primaryImage = product ? product.images.find((image) => image.is_primary) ?? product.images[0] : undefined;

    items.push({
      id: variant.id,
      variant_id: variant.id,
      product_id: variant.product_id,
      product_name: product?.name ?? variant.name,
      variant_name: variant.name,
      sku: variant.sku,
      quantity: line.quantity,
      unit_price: variant.price,
      subtotal: fromPaise(linePaise),
      image: primaryImage ? { url: primaryImage.url, alt_text: primaryImage.alt_text } : null,
    });
  }

  return {
    id: 'guest',
    items,
    subtotal: fromPaise(subtotalPaise),
    item_count: items.reduce((total, item) => total + item.quantity, 0),
  };
}

export async function getCartCount(): Promise<number> {
  try {
    const cart = await getCart();
    return cart.item_count;
  } catch {
    return 0;
  }
}
