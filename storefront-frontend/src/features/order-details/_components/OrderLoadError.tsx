import Link from 'next/link';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';

import styles from './OrderDetails.module.css';

/** The order could not be read for a reason other than "not yours / not found". */
export default function OrderLoadError() {
  return (
    <main className={styles.page}>
      <div className={homeStyles.container}>
        <nav className={styles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <Link href="/account/orders">My Orders</Link>
        </nav>
        <div className={styles.loadError} role="alert">
          <h1 className={styles.loadErrorTitle}>We couldn&apos;t load this order</h1>
          <p>Something went wrong reaching CliQ. Please try again in a moment.</p>
          <Link href="/account/orders" className={styles.outlineButton}>
            Back to My Orders
          </Link>
        </div>
      </div>
    </main>
  );
}
