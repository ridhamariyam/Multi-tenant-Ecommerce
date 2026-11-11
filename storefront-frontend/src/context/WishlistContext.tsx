'use client';

import { useRouter } from 'next/navigation';
import { createContext, useContext, useEffect, useMemo, useState, useTransition } from 'react';

import {
  addWishlistVariant,
  removeWishlistItem,
  toggleWishlistByProduct,
  type WishlistMutation,
} from '@/lib/wishlist/actions';
import type { Wishlist } from '@/types/cart';

interface WishlistContextType {
  wishlist: Wishlist;
  pending: boolean;
  error: string | null;
  isProductSaved: (productId: string) => boolean;
  isVariantSaved: (variantId: string) => boolean;
  /** For a listing card, which knows no variant. Resolves with any error message. */
  toggleProduct: (productId: string) => Promise<string | null>;
  /** For a product page, where a specific variant is already chosen. */
  toggleVariant: (variantId: string) => Promise<string | null>;
  removeItem: (itemId: string) => Promise<string | null>;
}

const WishlistContext = createContext<WishlistContextType | null>(null);

/**
 * The wishlist, held by the backend rather than in the browser.
 *
 * Mirrors CartContext: every mutation answers with the whole wishlist, and
 * a router refresh afterwards lets server-rendered views -- the wishlist
 * page itself -- see the same change.
 */
export function WishlistProvider({
  initialWishlist,
  children,
}: {
  initialWishlist: Wishlist;
  children: React.ReactNode;
}) {
  const router = useRouter();
  const [wishlist, setWishlist] = useState<Wishlist>(initialWishlist);
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  useEffect(() => {
    setWishlist(initialWishlist);
  }, [initialWishlist]);

  async function run(mutation: Promise<WishlistMutation>): Promise<string | null> {
    const result = await mutation;
    setWishlist(result.wishlist);
    setError(result.error);
    startTransition(() => router.refresh());
    return result.error;
  }

  const savedVariantIds = useMemo(
    () => new Set(wishlist.items.map(item => item.variant_id)),
    [wishlist.items],
  );
  const savedProductIds = useMemo(
    () => new Set(wishlist.items.map(item => item.product_id)),
    [wishlist.items],
  );

  function toggleVariant(variantId: string) {
    const existing = wishlist.items.find(item => item.variant_id === variantId);
    return run(existing ? removeWishlistItem(existing.id) : addWishlistVariant(variantId));
  }

  return (
    <WishlistContext.Provider
      value={{
        wishlist,
        pending,
        error,
        isProductSaved: productId => savedProductIds.has(productId),
        isVariantSaved: variantId => savedVariantIds.has(variantId),
        toggleProduct: productId => run(toggleWishlistByProduct(productId)),
        toggleVariant,
        removeItem: itemId => run(removeWishlistItem(itemId)),
      }}>
      {children}
    </WishlistContext.Provider>
  );
}

export function useWishlist() {
  const context = useContext(WishlistContext);

  if (!context) {
    throw new Error('useWishlist must be used inside WishlistProvider');
  }

  return context;
}
