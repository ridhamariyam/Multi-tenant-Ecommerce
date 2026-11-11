import type { Metadata } from 'next';

import styles from '../Info.module.css';
import TrackOrderForm from './TrackOrderForm';

export const metadata: Metadata = {
  title: 'Track your order | CliQ.',
  description: 'Follow your CliQ. order with its order number and the phone number you ordered with.',
  robots: { index: false },
};

/** Public order tracking, so guests (and anyone signed out) can follow an order. */
export default async function TrackOrderPage({ searchParams }: { searchParams: Promise<{ order?: string }> }) {
  const { order } = await searchParams;

  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Help</p>
        <h1 className={styles.title}>Track your order.</h1>
        <p className={styles.lead}>
          Enter your order number and the mobile number you placed the order with.
        </p>
        <TrackOrderForm initialOrderNumber={order ?? ''} />
      </div>
    </div>
  );
}
