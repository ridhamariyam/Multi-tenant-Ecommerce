import type { Metadata } from 'next';

import styles from '../Info.module.css';

export const metadata: Metadata = {
  title: 'Contact',
  alternates: { canonical: '/contact' },
  description: 'Reach the CliQ studio for help with orders, sizing, returns and anything else.',
};

export default function ContactPage() {
  return (
    <div className={styles.page}>
      <div className={styles.wrap}>
        <p className={styles.kicker}>Contact</p>
        <h1 className={styles.title}>Write to the CliQ studio.</h1>
        <p className={styles.lead}>
          For help with an order, sizing, returns or anything else, reach out and a member of the
          team will get back to you within one business day.
        </p>
        <div className={styles.contactGrid}>
          <div className={styles.contactCard}>
            <p className={styles.contactLabel}>Email</p>
            <p className={styles.contactValue}>
              <a href="mailto:hello@cliq.example">hello@cliq.example</a>
            </p>
          </div>
          <div className={styles.contactCard}>
            <p className={styles.contactLabel}>Orders &amp; Returns</p>
            <p className={styles.contactValue}>
              <a href="mailto:hello@cliq.example">hello@cliq.example</a>
            </p>
          </div>
          <div className={styles.contactCard}>
            <p className={styles.contactLabel}>Hours</p>
            <p className={styles.contactValue}>Mon&ndash;Sat, 10am&ndash;7pm IST</p>
          </div>
        </div>
      </div>
    </div>
  );
}
