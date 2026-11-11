import homeStyles from '../../../(home)/home/_components/luxe/Home.module.css';
import styles from '@/elements/SingleProductPage/luxe/ProductDetails.module.css';

/** Placeholder in the product page's own layout while the product loads. */
export default function ProductLoading() {
  return (
    <div className={homeStyles.page} aria-busy="true" aria-label="Loading product">
      <div className={homeStyles.container}>
        <div className={styles.layout}>
          <div className={`${styles.skeleton} ${styles.skeletonImage}`} />
          <div className={styles.skeletonDetails}>
            <div className={styles.skeleton} style={{ width: '70%', height: 26 }} />
            <div className={styles.skeleton} style={{ width: '25%', height: 16 }} />
            <div className={styles.skeleton} style={{ width: '100%', height: 48 }} />
            <div className={styles.skeleton} style={{ width: '100%', height: 40 }} />
            <div className={styles.skeleton} style={{ width: '100%', height: 44 }} />
          </div>
        </div>
      </div>
    </div>
  );
}
