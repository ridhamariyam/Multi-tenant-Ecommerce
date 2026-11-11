import type { Metadata } from 'next';

import { NO_INDEX } from '@/lib/seo';

import styles from '../Info.module.css';
import UnsubscribeButton from './UnsubscribeButton';

export const metadata: Metadata = { title: 'Unsubscribe', robots: NO_INDEX };

/**
 * From the link in a marketing email. It asks for a click rather than
 * unsubscribing on load, so mail scanners that open links change nothing.
 */
export default async function UnsubscribePage({ searchParams }: { searchParams: Promise<{ u?: string; t?: string }> }) {
  const { u, t } = await searchParams;
  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Email preferences</p>
        <h1 className={styles.title}>Stop marketing email?</h1>
        <p className={styles.lead}>You&apos;ll still get emails about your orders.</p>
        {u && t ? <UnsubscribeButton userId={u} token={t} /> : <p>This link is incomplete. Open it again from the email.</p>}
      </div>
    </div>
  );
}
