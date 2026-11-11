'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { BagIcon, HeartIcon, HomeIcon, UserIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useWishlist } from '@/context/WishlistContext';

// Shared with the Product Listing page, which already needs it for its own
// grid/card styles -- this reuses `.mobileBottomNav`/`.mobileNavItem`/etc.
// from there rather than duplicating the CSS.
import listingStyles from '@/components/luxe/Listing.module.css';

/**
 * App-style bottom tab bar (Home/Shop/Wishlist/Account), shown only on small
 * viewports. Originally built for the Product Listing page; promoted here
 * once the Wishlist page needed the same nav, so both pages render the one
 * real component instead of two copies drifting apart.
 *
 * The wishlist badge is the real saved-item count from WishlistContext; the
 * other tabs carry no counts because nothing real backs one here (cart count
 * already lives on the header's cart pill).
 */
export default function MobileBottomNav() {
  const pathname = usePathname();
  const { wishlist } = useWishlist();
  const wishlistCount = wishlist.items.length;

  const items = [
    { href: '/', label: 'Home', Icon: HomeIcon },
    { href: '/products', label: 'Shop', Icon: BagIcon },
    { href: '/wishlist', label: 'Wishlist', Icon: HeartIcon, badge: wishlistCount },
    { href: '/account', label: 'Account', Icon: UserIcon },
  ];

  return (
    <nav className={listingStyles.mobileBottomNav} aria-label="Mobile">
      {items.map(({ href, label, Icon, badge }) => {
        const active = pathname === href;
        return (
          <Link
            key={label}
            href={href}
            className={`${listingStyles.mobileNavItem} ${active ? listingStyles.mobileNavItemActive : ''}`}
            aria-current={active ? 'page' : undefined}
          >
            <span className={listingStyles.mobileNavIconWrap}>
              <Icon size={20} />
              {!!badge && <span className={listingStyles.mobileNavBadge}>{badge}</span>}
            </span>
            {label}
          </Link>
        );
      })}
    </nav>
  );
}
