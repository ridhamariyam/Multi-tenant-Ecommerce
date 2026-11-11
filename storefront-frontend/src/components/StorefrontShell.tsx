'use client';



import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { ToastContainer } from 'react-toastify';
import 'react-toastify/dist/ReactToastify.css';
import './StorefrontToast.css';

import ScrollToTopButton from '@/constant/ScrollToTopButton';
import { AuthProvider } from '@/context/AuthContext';
import { CartProvider } from '@/context/CartContext';
import { SignInModalProvider } from '@/context/SignInModalContext';
import { WishlistProvider } from '@/context/WishlistContext';
import CartDrawer from '@/components/luxe/CartDrawer';
import type { UserProfile } from '@/types/auth';
import type { Cart, Wishlist } from '@/types/cart';

/**
 * The template's browser-side chrome, split out of the layout.
 *
 * The layout itself has to be a server component so it can read the session
 * cookie and the cart before rendering; the vendor CSS, the WOW animations
 * and the providers all need the browser, so they live here and receive
 * what the server resolved as props.
 */
export default function StorefrontShell({
  user,
  cart,
  wishlist,
  children,
}: {
  user: UserProfile | null;
  cart: Cart;
  wishlist: Wishlist;
  children: React.ReactNode;
}) {
  const path = usePathname();

  useEffect(() => {
    setTimeout(() => {
      const links = document.querySelectorAll('a[href="#"]');
      const handleClick = (event: any) => {
        event.preventDefault();
      };
      if (links) {
        links.forEach(link => {
          link.addEventListener('click', handleClick);
        });
      }
    }, 600);
  }, [path]);

  useEffect(() => {
    setTimeout(() => {
      const { WOW } = require('wowjs');
      const wow = new WOW({
        boxClass: 'wow',
        animateClass: 'animated',
        offset: 0,
        mobile: false,
        once: true,
        live: false,
        callback: function (box: HTMLElement) {
          box.classList.add('will-animate');
          box.classList.add('animated');
        },
      });
      wow.init();
    }, 100);
  }, [path]);

  return (
    <>
      <AuthProvider user={user}>
        <SignInModalProvider>
          <CartProvider initialCart={cart}>
            <WishlistProvider initialWishlist={wishlist}>
              {children}
              <CartDrawer />
            </WishlistProvider>
          </CartProvider>
        </SignInModalProvider>
      </AuthProvider>
      {path !== '/' && path !== '/home' && <ScrollToTopButton />}
      <ToastContainer
        position="top-right"
        autoClose={3200}
        closeOnClick={false}
        hideProgressBar
        pauseOnFocusLoss
        pauseOnHover
        role="status"
      />
    </>
  );
}
