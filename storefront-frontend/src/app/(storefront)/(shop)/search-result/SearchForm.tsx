'use client';

import { useEffect, useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

import styles from './SearchResults.module.css';

export default function SearchForm({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [pending, startTransition] = useTransition();

  useEffect(() => setQuery(initialQuery), [initialQuery]);

  function runSearch() {
    const trimmed = query.trim();
    setQuery(trimmed);
    startTransition(() => {
      router.push(trimmed ? `/search-result?q=${encodeURIComponent(trimmed)}` : '/search-result');
    });
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    runSearch();
  }

  function clear() {
    setQuery('');
    startTransition(() => router.push('/search-result'));
  }

  return (
    <form action="/search-result" method="get" onSubmit={submit} role="search" className={styles.searchForm}>
      <label htmlFor="storefront-search" className={styles.visuallyHidden}>
        Search products
      </label>
      <div className={styles.searchControl}>
        <svg className={styles.searchIcon} viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="10.8" cy="10.8" r="6.8" />
          <path d="m16 16 4.3 4.3" />
        </svg>
        <input
          id="storefront-search"
          type="search"
          name="q"
          value={query}
          onChange={event => setQuery(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter') {
              event.preventDefault();
              runSearch();
            }
          }}
          placeholder="Search by product, category or keyword"
          autoComplete="off"
          aria-describedby="search-help"
        />
        {query && (
          <button type="button" className={styles.clearButton} onClick={clear} disabled={pending}>
            Clear
          </button>
        )}
        <button type="submit" className={styles.searchButton} disabled={pending}>
          {pending ? 'Searching…' : 'Search'}
        </button>
      </div>
      <span id="search-help" className={styles.visuallyHidden}>
        Enter a product name, category, brand or keyword. Whitespace is ignored.
      </span>
    </form>
  );
}
