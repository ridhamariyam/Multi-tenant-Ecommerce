import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';

import styles from './_components/MyOrders.module.css';

/** Placeholder in the order list's own layout while the orders load. */
export default function MyOrdersLoading() {
  return (
    <div className={styles.page} aria-busy="true" aria-label="Loading your orders">
      <section className={`${homeStyles.container} ${styles.intro}`}>
        <div className={styles.skeleton} style={{ width: 140, height: 12, marginBottom: 16 }} />
        <div className={styles.skeleton} style={{ width: 220, height: 32 }} />
        <div className={styles.skeleton} style={{ width: 260, height: 14, marginTop: 14 }} />
      </section>
      <section className={`${homeStyles.container} ${styles.listing}`}>
        <div className={styles.skeleton} style={{ width: '100%', maxWidth: 640, height: 38, marginBottom: 28 }} />
        <div className={styles.list}>
          {[0, 1, 2].map(index => (
            <div key={index} className={styles.card}>
              <div className={`${styles.thumb} ${styles.skeleton}`} />
              <div className={styles.body}>
                <div className={styles.skeleton} style={{ width: '45%', height: 16 }} />
                <div className={styles.skeleton} style={{ width: '30%', height: 12 }} />
                <div className={styles.skeleton} style={{ width: '20%', height: 16 }} />
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
