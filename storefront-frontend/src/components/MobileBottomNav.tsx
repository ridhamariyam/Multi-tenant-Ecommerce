'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

import { useWishlist } from '@/context/WishlistContext';

import styles from './MobileBottomNav.module.css';

function HomeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 10.5 12 3l9 7.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5.5 9.5V20a1 1 0 0 0 1 1H9a1 1 0 0 0 1-1v-4a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1v4a1 1 0 0 0 1 1h2.5a1 1 0 0 0 1-1V9.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ShopIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M6 8h12l1 12.5a1 1 0 0 1-1 1.5H6a1 1 0 0 1-1-1.5L6 8Z" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function HeartIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path
        d="M12 20.5s-7.5-4.6-9.8-9.3C.6 7.7 2.3 4.5 5.6 4a4.6 4.6 0 0 1 6.4 2 4.6 4.6 0 0 1 6.4-2c3.3.5 5 3.7 3.4 7.2C19.5 15.9 12 20.5 12 20.5Z"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UserIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20.5c1.4-3.6 4.2-5.5 7.5-5.5s6.1 1.9 7.5 5.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

const NAV_ITEMS = [
  { href: '/', label: 'Home', Icon: HomeIcon },
  { href: '/products', label: 'Shop', Icon: ShopIcon },
  { href: '/wishlist', label: 'Wishlist', Icon: HeartIcon },
  { href: '/account', label: 'Account', Icon: UserIcon },
] as const;

export default function MobileBottomNav() {
  const pathname = usePathname();
  const { wishlist } = useWishlist();

  return (
    <nav className={styles.nav} aria-label="Primary">
      {NAV_ITEMS.map(({ href, label, Icon }) => {
        const active = pathname === href;

        return (
          <Link key={href} href={href} className={`${styles.item} ${active ? styles.active : ''}`}>
            <span className={styles.iconWrap}>
              <Icon />
              {label === 'Wishlist' && wishlist.item_count > 0 && (
                <span className={styles.badge}>{wishlist.item_count}</span>
              )}
            </span>
            <span className={styles.label}>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
