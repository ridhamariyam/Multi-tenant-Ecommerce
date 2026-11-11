import styles from './SearchResults.module.css';

export default function SearchResultsLoading() {
  return (
    <main className={styles.page} aria-busy="true" aria-live="polite">
      <div className={styles.container}>
        <p className={styles.resultMeta}>Searching CliQ products…</p>
        <div className={styles.grid}>
          {Array.from({ length: 8 }, (_, index) => (
            <div key={index} className={styles.loadingCard} />
          ))}
        </div>
      </div>
    </main>
  );
}
