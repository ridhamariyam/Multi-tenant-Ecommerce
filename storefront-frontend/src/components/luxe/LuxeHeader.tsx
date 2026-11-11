'use client';

import Link from 'next/link';
import { type CSSProperties, useState } from 'react';

import styles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import {
  BagIcon,
  ChevronDownIcon,
  CloseIcon,
  MenuIcon,
  SearchIcon,
} from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import HeaderSearch from '@/components/luxe/HeaderSearch';
import LuxeAccountNav from '@/components/luxe/LuxeAccountNav';
import LuxeWishlistButton from '@/components/luxe/LuxeWishlistButton';
import { useCart } from '@/context/CartContext';

const NAV_LINKS = [
  { label: 'Shop', href: '/products', chevron: true },
  { label: 'Best Sellers', href: '/products' },
  { label: 'About', href: '/about' },
  { label: 'Contact', href: '/contact' },
];

function CartButton({ className }: { className: string }) {
  const { itemCount } = useCart();
  return (
    <Link
      href="/cart"
      className={className}
      data-cart-trigger
      aria-label={itemCount > 0 ? `Cart, ${itemCount} items` : 'My cart'}>
      <BagIcon size={20} />
      {itemCount > 0 && (
        <span className={styles.headerBadge} aria-hidden="true">
          {itemCount > 99 ? '99+' : itemCount}
        </span>
      )}
    </Link>
  );
}

/**
 * The editorial bar used on the home page: small-caps navigation on the
 * left, the official stacked logo centred, utilities right.
 * Same links, account, wishlist and cart as every other page.
 */
function HomeHeader() {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);

  return (
    <header className={styles.homeHeader} data-storefront-header>
      <div className={styles.homeHeaderInner}>
        <nav aria-label="Primary" className={styles.homeNavWrap}>
          <ul className={styles.homeNav}>
            {NAV_LINKS.map((link, i) => (
              <li key={link.label} style={{ '--i': i } as CSSProperties}>
                <Link href={link.href}>
                  {link.label}
                  {link.chevron && <ChevronDownIcon size={11} />}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <button
          type="button"
          className={styles.homeMenuBtn}
          aria-label={mobileNavOpen ? 'Close menu' : 'Open menu'}
          aria-expanded={mobileNavOpen}
          onClick={() => setMobileNavOpen(v => !v)}
        >
          {mobileNavOpen ? <CloseIcon size={21} /> : <MenuIcon size={21} />}
        </button>

        <Link href="/" className={`${styles.homeLogo} ${styles.homeHeaderFade}`} aria-label="CliQ. home" data-home-logo>
          <span className={styles.homeLogoSymbol} aria-hidden="true" />
          <span className={styles.homeLogoMark} data-home-logo-wordmark aria-hidden="true" />
        </Link>

        <div className={`${styles.homeHeaderRight} ${styles.homeHeaderFade}`}>
          <button
            type="button"
            className={styles.headerIconBtn}
            aria-label="Search"
            aria-expanded={searchOpen}
            onClick={() => setSearchOpen(v => !v)}>
            <SearchIcon size={20} />
          </button>
          <LuxeAccountNav />
          <LuxeWishlistButton />
          <CartButton className={styles.headerRoundBtn} />
        </div>
      </div>

      <nav
        aria-label="Mobile"
        className={`${styles.homeMobileNav} ${mobileNavOpen ? styles.homeMobileNavOpen : ''}`}
      >
        {NAV_LINKS.map(link => (
          <Link key={link.label} href={link.href} onClick={() => setMobileNavOpen(false)}>
            {link.label}
          </Link>
        ))}
      </nav>

      <HeaderSearch open={searchOpen} onClose={() => setSearchOpen(false)} />
    </header>
  );
}

/**
 * The CliQ header, shared by every page that opts into the luxe design
 * system. Lifted verbatim out of the Home page's header markup (Home.module.css
 * stays the single source of truth for its styling) so other pages can look
 * identical without the Home page itself importing or re-exporting anything.
 * The home page itself gets the editorial variant above.
 */
export default function LuxeHeader() {
  return <HomeHeader />;
}
