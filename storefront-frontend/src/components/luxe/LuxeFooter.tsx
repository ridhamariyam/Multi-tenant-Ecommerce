'use client';

import Link from 'next/link';

import styles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';

const SHOP_LINKS = [
  { label: 'New Arrivals', href: '/products' },
  { label: 'Collections', href: '/products' },
  { label: 'Best Sellers', href: '/products' },
  { label: 'Wishlist', href: '/wishlist' },
  { label: 'Track Order', href: '/track-order' },
];

const ABOUT_LINKS = [
  { label: 'Our Story', href: '/about' },
  { label: 'Sustainability', href: '/about' },
  { label: 'FAQs', href: '/faq' },
  { label: 'Shipping & Returns', href: '/policies/shipping-returns' },
  { label: 'Account', href: '/account' },
];

/** Payment options the storefront checkout already offers. */
const PAYMENTS = ['UPI', 'Cards', 'Net Banking', 'Cash on Delivery'];

/**
 * The home page's footer: a concise contact note above the existing link
 * columns, closed by the CliQ lockup in Champagne Gold.
 */
function HomeFooter() {
  return (
    <footer className={styles.homeFooter}>
      <div className={styles.footerContact}>
        <p className={styles.footerContactQuestion}>Have any questions or concerns?</p>
        <p className={styles.footerContactCopy}>
          For any assistance, reach out to us at{' '}
          <a href="mailto:hello@cliq.example" className={styles.footerContactEmail}>
            hello@cliq.example
          </a>
          .
        </p>
      </div>

      <div className={styles.footerGrid}>
        <div>
          <p className={styles.footerLabel}>Contact</p>
          <p className={styles.footerBig}>
            <Link href="/contact">Write to the CliQ studio</Link>
          </p>
        </div>
        <ul className={styles.footerLinks}>
          {SHOP_LINKS.map(link => (
            <li key={link.label}>
              <Link href={link.href}>{link.label}</Link>
            </li>
          ))}
        </ul>
        <ul className={styles.footerLinks}>
          {ABOUT_LINKS.map(link => (
            <li key={link.label}>
              <Link href={link.href}>{link.label}</Link>
            </li>
          ))}
        </ul>
      </div>

      <div className={styles.footerBottom}>
        <span className={styles.footerLogoLockup} role="img" aria-label="CliQ.">
          <span className={styles.footerLogoSymbol} />
          <span className={styles.footerLogoWordmark} />
        </span>
        <div>
          <p className={styles.footerLabel}>We accept</p>
          <ul className={styles.footerPayments}>
            {PAYMENTS.map(method => (
              <li key={method}>{method}</li>
            ))}
          </ul>
        </div>
        <div className={styles.footerLegal}>
          <p className={styles.footerLabel}>Legal</p>
          <Link href="/policies/privacy">Privacy policy</Link>
          {' / '}
          <Link href="/policies/terms">Terms</Link>
        </div>
      </div>
    </footer>
  );
}

/** The CliQ footer, shared by every page in the luxe design system. See LuxeHeader for why it's a copy, not an import, of the Home page's own markup. */
export default function LuxeFooter() {
  return <HomeFooter />;
}
