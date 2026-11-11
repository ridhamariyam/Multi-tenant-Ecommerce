'use client';

import { useRouter } from 'next/navigation';
import { createContext, useContext, useEffect, useRef, useState, useTransition } from 'react';

import { addCartItem, clearCart, removeCartLine, setCartItemQuantity } from '@/lib/cart/actions';
import type { Cart, CartItem } from '@/types/cart';

interface CartContextType {
  cart: Cart;
  items: CartItem[];
  itemCount: number;
  pending: boolean;
  error: string | null;
  cartDrawerOpen: boolean;
  closeCartDrawer: () => void;
  openCartDrawer: () => void;
  /** Each mutation resolves to the API's error message, or null when it succeeded. */
  addToCart: (variantId: string, quantity: number, options?: { openDrawer?: boolean }) => Promise<string | null>;
  updateQuantity: (itemId: string, quantity: number) => Promise<string | null>;
  removeFromCart: (itemId: string) => Promise<string | null>;
  clearCart: () => Promise<string | null>;
}

const CartContext = createContext<CartContextType | null>(null);

/**
 * The cart, held by the backend rather than in the browser.
 *
 * Every mutation answers with the whole cart, so prices, line subtotals and
 * stock always come from the API and are never recomputed here. Every cart
 * view (header badge, drawer, cart page, checkout) reads this context, so no
 * router refresh is needed -- refreshing re-rendered the whole page, which
 * looked like a reload on every add to cart.
 */
export function CartProvider({ initialCart, children }: { initialCart: Cart; children: React.ReactNode }) {
  const [cart, setCart] = useState<Cart>(initialCart);
  const [error, setError] = useState<string | null>(null);
  const [mutationCount, setMutationCount] = useState(0);
  const [cartDrawerOpen, setCartDrawerOpen] = useState(false);

  useEffect(() => {
    setCart(initialCart);
  }, [initialCart]);

  async function run(mutation: Promise<{ cart: Cart; error: string | null }>, openDrawerOnSuccess = false) {
    setMutationCount(count => count + 1);
    try {
      const result = await mutation;

      setCart(result.cart);
      setError(result.error);
      if (openDrawerOnSuccess && !result.error) setCartDrawerOpen(true);

      return result.error;
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : 'We could not update your cart. Please try again.';
      setError(message);
      return message;
    } finally {
      setMutationCount(count => Math.max(0, count - 1));
    }
  }

  return (
    <CartContext.Provider
      value={{
        cart,
        items: cart.items,
        itemCount: cart.item_count,
        pending: mutationCount > 0,
        error,
        cartDrawerOpen,
        openCartDrawer: () => setCartDrawerOpen(true),
        closeCartDrawer: () => setCartDrawerOpen(false),
        addToCart: (variantId, quantity, options) => run(addCartItem(variantId, quantity), options?.openDrawer ?? true),
        updateQuantity: (itemId, quantity) => run(setCartItemQuantity(itemId, quantity)),
        removeFromCart: itemId => run(removeCartLine(itemId)),
        clearCart: () => run(clearCart()),
      }}>
      {children}
    </CartContext.Provider>
  );
}

export function useCart() {
  const context = useContext(CartContext);

  if (!context) {
    throw new Error('useCart must be used inside CartProvider');
  }

  return context;
}

/**
 * For pages whose numbers are priced on the server from the cart (the cart
 * page's and checkout's preview: discount, shipping, tax, total). When the
 * cart changes on such a page, re-fetch it so those totals never go stale.
 * Other pages don't use this, so adding to cart there doesn't re-render them.
 */
export function useRefreshOnCartChange() {
  const { cart } = useCart();
  const router = useRouter();
  const [refreshing, startTransition] = useTransition();
  const seen = useRef(cart);

  useEffect(() => {
    if (seen.current === cart) return;
    seen.current = cart;
    startTransition(() => router.refresh());
  }, [cart, router]);

  return refreshing;
}
