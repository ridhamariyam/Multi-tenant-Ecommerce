import styles from '../_components/Invoice.module.css';

export default function InvoiceLoading() {
  return (
    <main className={styles.errorPage} aria-busy="true" aria-label="Loading invoice">
      <section className={styles.errorPanel}>
        <h1>Loading your invoice</h1>
        <p>We’re retrieving the official invoice for this order.</p>
      </section>
    </main>
  );
}
