'use client';

import { useEffect, useRef, useState } from 'react';

import BrandLogo from '@/components/BrandLogo';
import { useAuth } from '@/context/AuthContext';
import { useBrand } from '@/context/BrandContext';
import { useSignInModal } from '@/context/SignInModalContext';
import { addCartItem } from '@/lib/cart/actions';

interface AddRequest {
  variantIds: string[];
  resolve: (result: { added: string[]; error: string | null }) => void;
}

/**
 * The CliQ. header plus the bridge between the vanilla runway element and
 * the storefront cart.
 *
 * The element dispatches `cliq:add-to-cart` with variant ids; each one goes
 * through the same `addCartItem` server action the rest of the storefront
 * uses, so guest carts (cookie) and signed-in carts (API) both work and
 * stock is checked by the backend. The element is told exactly which ids
 * made it in, so a partial failure marks only those pieces as added.
 */
export default function RunwayClient({ initialCount }: { initialCount: number }) {
  const { isSignedIn } = useAuth();
  const brand = useBrand();
  const { openSignIn } = useSignInModal();
  const [count, setCount] = useState(initialCount);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => setCount(initialCount), [initialCount]);

  useEffect(() => {
    import('./runway-element.js');

    const showToast = (message: string) => {
      setToast(message);
      clearTimeout(toastTimer.current);
      toastTimer.current = setTimeout(() => setToast(null), 2500);
    };

    const onAdd = (event: Event) => {
      const { variantIds, resolve } = (event as CustomEvent<AddRequest>).detail;
      event.preventDefault();

      (async () => {
        const added: string[] = [];
        let error: string | null = null;

        for (const id of variantIds) {
          try {
            const result = await addCartItem(id, 1);
            setCount(result.cart.item_count);
            if (result.error) {
              error = result.error;
              break;
            }
            added.push(id);
          } catch {
            error = 'Couldn’t add to bag. Please try again.';
            break;
          }
        }

        if (added.length) showToast(added.length > 1 ? 'Look added to your bag' : 'Piece added to your bag');
        resolve({ added, error });
      })();
    };

    document.addEventListener('cliq:add-to-cart', onAdd);
    return () => {
      document.removeEventListener('cliq:add-to-cart', onAdd);
      clearTimeout(toastTimer.current);
    };
  }, []);

  return (
    <>
      <header className="site-header shopify-section-group-header-group">
        <a href="/" className="brand" aria-label={`${brand.name} home`}>
          <BrandLogo cliqMark="CliQ." className="brand-logo" />
        </a>
        <nav aria-label="Main navigation">
          <a href="/">Home</a>
          <a href="/products">Shop</a>
          <a href="/about">About</a>
          {isSignedIn ? (
            <a href="/account">My Account</a>
          ) : (
            <button type="button" className="nav-signin" onClick={() => openSignIn()}>
              Login
            </button>
          )}
        </nav>
        <a href="/cart" className="bag-link" aria-label={`Open bag, ${count} ${count === 1 ? 'item' : 'items'}`}>
          <svg width="22" height="24" viewBox="0 0 24 26" fill="none" stroke="currentColor" strokeWidth="1.3" aria-hidden="true">
            <path d="M4 8h16l1 16H3L4 8zM8 8V6a4 4 0 0 1 8 0v2" />
          </svg>
          <span data-cart-count>{count}</span>
        </a>
      </header>
      <div className={`cliq-toast${toast ? ' is-on' : ''}`} role="status" aria-live="polite">
        {toast}
        {toast ? <a href="/cart">View bag</a> : null}
      </div>
    </>
  );
}
