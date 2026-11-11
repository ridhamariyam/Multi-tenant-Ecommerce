import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';

import styles from './_components/OrderSuccess.module.css';

export default function OrderSuccessLoading() {
  return (
    <main className={styles.page} aria-busy="true" aria-label="Loading order confirmation">
      <div className={`${homeStyles.container} ${styles.container}`}>
        <div className={styles.hero}>
          <span className={styles.statusIcon} />
          <p className={styles.eyebrow}>Order update</p>
          <h1 className={styles.heading}>Loading your order</h1>
          <p className={styles.message}>We’re retrieving the latest order and payment status.</p>
        </div>
        <div className={styles.contentGrid}>
          <section className={styles.panel} />
          <section className={styles.panel} />
        </div>
      </div>
    </main>
  );
}
