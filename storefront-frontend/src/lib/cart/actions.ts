'use server';

import { revalidatePath } from 'next/cache';

import { cartApi, wishlistApi } from '@/lib/api/cart';
import { catalogueApi } from '@/lib/api/catalogue';
import { ApiError, ApiUnreachableError } from '@/lib/api/errors';
import { getActionAccessToken } from '@/lib/auth/session';
import { addLine, clearGuestCart, readGuestCart, writeGuestCart } from '@/lib/cart/guest-cart';
import { getCart } from '@/lib/cart/read';
import type { CartActionState, CartMutation } from '@/lib/cart/state';
import type { ProductSummaryStorefront, VariantStorefront } from '@/types/catalogue';

function toState(error: unknown): CartActionState {
  if (error instanceof ApiError) {
    if (error.isRateLimited) return { status: 'error', message: 'Too many requests. Try again shortly.' };
    return { status: 'error', message: error.message };
  }

  if (error instanceof ApiUnreachableError) {
    return { status: 'error', message: 'Could not reach CliQ. Try again in a moment.' };
  }

  throw error;
}

function refreshCartViews(): void {
  revalidatePath('/cart');
  revalidatePath('/', 'layout');
}

export async function addToCart(
  _previous: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const variantId = String(formData.get('variant_id') ?? '');
  const quantity = Number(formData.get('quantity') ?? 1);

  if (!variantId) return { status: 'error', message: 'Choose an option first.' };
  if (!Number.isInteger(quantity) || quantity < 1) {
    return { status: 'error', message: 'Choose a quantity.' };
  }

  const token = await getActionAccessToken();

  if (token) {
    try {
      await cartApi.addItem(token, variantId, quantity);
    } catch (error) {
      return toState(error);
    }
  } else {
    const lines = await readGuestCart();
    await writeGuestCart(addLine(lines, variantId, quantity));
  }

  refreshCartViews();
  return { status: 'success', message: 'Added to your cart' };
}

export async function updateCartQuantity(
  _previous: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get('item_id') ?? '');
  const quantity = Number(formData.get('quantity') ?? 1);

  const token = await getActionAccessToken();

  if (token) {
    try {
      await cartApi.updateItem(token, itemId, quantity);
    } catch (error) {
      return toState(error);
    }
  } else {
    const lines = await readGuestCart();
    await writeGuestCart(
      lines.map((line) => (line.variant_id === itemId ? { ...line, quantity } : line)),
    );
  }

  refreshCartViews();
  return { status: 'success', message: 'Cart updated' };
}

export async function removeCartItem(
  _previous: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const itemId = String(formData.get('item_id') ?? '');
  const token = await getActionAccessToken();

  if (token) {
    try {
      await cartApi.removeItem(token, itemId);
    } catch (error) {
      return toState(error);
    }
  } else {
    const lines = await readGuestCart();
    await writeGuestCart(lines.filter((line) => line.variant_id !== itemId));
  }

  refreshCartViews();
  return { status: 'success', message: 'Removed from your cart' };
}

export async function mergeGuestCart(token: string): Promise<{ merged: number; rejected: number }> {
  const lines = await readGuestCart();
  if (lines.length === 0) return { merged: 0, rejected: 0 };

  let merged = 0;
  let rejected = 0;

  for (const line of lines) {
    try {
      await cartApi.addItem(token, line.variant_id, line.quantity);
      merged += 1;
    } catch {
      rejected += 1;
    }
  }

  await clearGuestCart();
  refreshCartViews();

  return { merged, rejected };
}

export async function toggleWishlist(
  _previous: CartActionState,
  formData: FormData,
): Promise<CartActionState> {
  const variantId = String(formData.get('variant_id') ?? '');
  const itemId = String(formData.get('item_id') ?? '');

  const token = await getActionAccessToken();
  if (!token) return { status: 'error', message: 'Sign in to save pieces to your wishlist.' };

  try {
    if (itemId) {
      await wishlistApi.removeItem(token, itemId);
      revalidatePath('/wishlist');
      return { status: 'success', message: 'Removed from your wishlist' };
    }

    await wishlistApi.addItem(token, variantId);
    revalidatePath('/wishlist');
    return { status: 'success', message: 'Saved to your wishlist' };
  } catch (error) {
    return toState(error);
  }
}

async function mutate(apply: (token: string | null) => Promise<void>): Promise<CartMutation> {
  const token = await getActionAccessToken();

  try {
    await apply(token);
  } catch (error) {
    const state = toState(error);
    return { cart: await getCart(), error: state.message };
  }

  // No revalidatePath here: it makes Next re-render the whole current page in
  // the action response, which looks like a page reload. The caller gets the
  // fresh cart back and CartContext pushes it to every cart view.
  return { cart: await getCart(), error: null };
}

async function assertGuestStock(variantId: string, requestedQuantity: number): Promise<void> {
  const variant = await catalogueApi.getVariant(variantId);

  if (!variant.in_stock || variant.available_quantity < 1) {
    throw new ApiError({
      status: 409,
      code: 'OUT_OF_STOCK',
      message: 'This item is currently unavailable.',
    });
  }

  if (requestedQuantity > variant.available_quantity) {
    throw new ApiError({
      status: 409,
      code: 'INSUFFICIENT_STOCK',
      message: `Only ${variant.available_quantity} available. Please adjust the quantity.`,
    });
  }
}

export async function addCartItem(variantId: string, quantity: number): Promise<CartMutation> {
  if (!variantId) return { cart: await getCart(), error: 'Choose an option first.' };
  if (!Number.isInteger(quantity) || quantity < 1) {
    return { cart: await getCart(), error: 'Choose a valid quantity.' };
  }

  return mutate(async token => {
    if (token) {
      await cartApi.addItem(token, variantId, quantity);
      return;
    }

    const lines = await readGuestCart();
    const existingQuantity = lines.find(line => line.variant_id === variantId)?.quantity ?? 0;
    await assertGuestStock(variantId, existingQuantity + quantity);
    await writeGuestCart(addLine(lines, variantId, quantity));
  });
}

export async function setCartItemQuantity(itemId: string, quantity: number): Promise<CartMutation> {
  if (quantity < 1) return removeCartLine(itemId);

  return mutate(async token => {
    if (token) {
      await cartApi.updateItem(token, itemId, quantity);
      return;
    }

    const lines = await readGuestCart();
    const line = lines.find(item => item.variant_id === itemId);
    if (line) await assertGuestStock(itemId, quantity);
    await writeGuestCart(
      lines.map(line => (line.variant_id === itemId ? { ...line, quantity } : line)),
    );
  });
}

export async function removeCartLine(itemId: string): Promise<CartMutation> {
  return mutate(async token => {
    if (token) {
      await cartApi.removeItem(token, itemId);
      return;
    }

    const lines = await readGuestCart();
    await writeGuestCart(lines.filter(line => line.variant_id !== itemId));
  });
}

export async function clearCart(): Promise<CartMutation> {
  return mutate(async token => {
    if (token) {
      await cartApi.clear(token);
      return;
    }

    await clearGuestCart();
  });
}

/**
 * Public catalogue data used only while the cart drawer is open. Variant
 * stock/options come from the existing variant endpoint so the drawer can
 * show the selected values and prevent quantity increments past live stock.
 */
export async function getCartDrawerContent(
  excludedProductIds: string[],
  variantIds: string[],
): Promise<{ recommendations: ProductSummaryStorefront[]; variants: Record<string, VariantStorefront | null> }> {
  const [page, ...variantResults] = await Promise.all([
    catalogueApi.listProducts({ page_size: 20, sort: 'newest' }).catch(() => null),
    ...[...new Set(variantIds)].map(id => catalogueApi.getVariant(id).catch(() => null)),
  ]);

  const excluded = new Set(excludedProductIds);
  const recommendations = (page?.items ?? [])
    .filter(product => product.in_stock && !excluded.has(product.id))
    .slice(0, 4);
  const ids = [...new Set(variantIds)];
  const variants = Object.fromEntries(ids.map((id, index) => [id, variantResults[index] ?? null]));

  return { recommendations, variants };
}
