import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';

import styles from '../_components/OrderDetails.module.css';

/** Placeholder in the order page's own layout while the order loads. */
export default function OrderDetailsLoading() {
  return (
    <main className={styles.page} aria-busy="true" aria-label="Loading order">
      <section className={`${homeStyles.container} ${styles.intro}`}>
        <div className={styles.skeleton} style={{ width: 220, height: 12, marginBottom: 16 }} />
        <div className={styles.skeleton} style={{ width: 280, height: 32 }} />
        <div className={styles.skeleton} style={{ width: 160, height: 14, marginTop: 14 }} />
      </section>
      <section className={`${homeStyles.container} ${styles.content}`}>
        <div className={styles.mainGrid}>
          <div className={styles.leftColumn}>
            <div className={`${styles.card} ${styles.skeleton}`} style={{ height: 180 }} />
            <div className={`${styles.card} ${styles.skeleton}`} style={{ height: 140 }} />
          </div>
          <div className={`${styles.card} ${styles.skeleton}`} style={{ height: 240 }} />
        </div>
      </section>
    </main>
  );
}
