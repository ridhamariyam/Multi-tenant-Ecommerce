import StorefrontShell from '@/components/StorefrontShell';
import LuxeFooter from '@/components/luxe/LuxeFooter';
import LuxeHeader from '@/components/luxe/LuxeHeader';
import layoutStyles from '@/app/(storefront)/StorefrontLayout.module.css';
import NotFoundPage from '@/app/(storefront)/_components/not-found/NotFoundPage';
import { getCurrentUser } from '@/lib/auth/current-user';
import { getCart } from '@/lib/cart/read';
import { EMPTY_WISHLIST, getWishlist } from '@/lib/wishlist/read';
import type { Cart } from '@/types/cart';

export const metadata = {
  title: 'Page Not Found | CliQ.',
  description: "The page you're looking for doesn't exist or may have been moved.",
};

const EMPTY_CART: Cart = { id: 'guest', items: [], subtotal: '0.00', item_count: 0 };

export default async function RootNotFound() {
  const [user, cart, wishlist] = await Promise.all([
    getCurrentUser().catch(() => null),
    getCart().catch(() => EMPTY_CART),
    getWishlist().catch(() => EMPTY_WISHLIST),
  ]);

  // Rendered inside app/layout.tsx, which owns <html>, <head> and the fonts.
  return (
    <StorefrontShell user={user} cart={cart} wishlist={wishlist}>
      <div className={`page-wraper ${layoutStyles.shell}`}>
        <LuxeHeader />
        <main className={layoutStyles.content}><NotFoundPage /></main>
        <LuxeFooter />
      </div>
    </StorefrontShell>
  );
}
