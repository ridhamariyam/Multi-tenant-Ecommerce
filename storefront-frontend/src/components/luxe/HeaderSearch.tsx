'use client';

import Image from 'next/image';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { CloseIcon, SearchIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { catalogueApi } from '@/lib/api/catalogue';
import { searchApi } from '@/lib/api/search';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatPriceRange } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import type { ProductStorefront } from '@/types/catalogue';

import styles from './HeaderSearch.module.css';

const SEARCH_DEBOUNCE_MS = 300;
const MIN_QUERY_LENGTH = 2;
const RESULT_LIMIT = 8;

type Status = 'idle' | 'loading' | 'done' | 'error';

function productHref(product: ProductStorefront): string {
  return product.slug
    ? `/products/${encodeURIComponent(product.slug)}`
    : `/single-product/${product.id}`;
}

/**
 * The header's search drop-down: opens under the bar, searches as the
 * shopper types and lists matches in place, so there is no trip to a
 * separate results page.
 *
 * Search rows carry no image or slug, so each hit is fetched in full --
 * same as the results page does.
 */
export default function HeaderSearch({ open, onClose }: { open: boolean; onClose: () => void }) {
  const pathname = usePathname();
  const inputRef = useRef<HTMLInputElement>(null);
  const requestRef = useRef(0);
  const [term, setTerm] = useState('');
  const [status, setStatus] = useState<Status>('idle');
  const [products, setProducts] = useState<ProductStorefront[]>([]);
  const [total, setTotal] = useState(0);

  async function runSearch(query: string) {
    const request = ++requestRef.current;
    setStatus('loading');

    try {
      const results = await searchApi.searchProducts({ q: query, size: RESULT_LIMIT });
      const detailed = await Promise.allSettled(results.items.map(item => catalogueApi.getProduct(item.id)));
      if (request !== requestRef.current) return;

      setProducts(
        detailed.flatMap(result => (result.status === 'fulfilled' ? [result.value] : [])),
      );
      setTotal(results.meta.total_items);
      setStatus('done');
    } catch {
      if (request !== requestRef.current) return;
      setStatus('error');
    }
  }

  // Search as the shopper types, once they pause.
  useEffect(() => {
    const query = term.trim();
    if (query.length < MIN_QUERY_LENGTH) {
      requestRef.current++;
      setProducts([]);
      setStatus('idle');
      return;
    }

    const timer = setTimeout(() => runSearch(query), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [term]);

  useEffect(() => {
    if (!open) return;

    inputRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  // Following a result navigates away; close behind it.
  useEffect(() => {
    onClose();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);

  if (!open) return null;

  const query = term.trim();

  return (
    <>
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />

      <form
        className={styles.bar}
        role="search"
        onSubmit={event => {
          event.preventDefault();
          if (query.length >= MIN_QUERY_LENGTH) runSearch(query);
        }}>
        <SearchIcon size={18} className={styles.barIcon} />
        <label htmlFor="header-search" className={styles.visuallyHidden}>
          Search products
        </label>
        <input
          ref={inputRef}
          id="header-search"
          type="search"
          value={term}
          onChange={event => setTerm(event.target.value)}
          placeholder="Search by product, category or keyword"
          autoComplete="off"
          className={styles.input}
        />
        <button type="button" className={styles.closeBtn} onClick={onClose} aria-label="Close search">
          <CloseIcon size={18} />
        </button>
      </form>

      {(query.length >= MIN_QUERY_LENGTH || status !== 'idle') && (
        <div className={styles.body} aria-live="polite">
          {status === 'idle' && (
            <p className={styles.message}>Type at least {MIN_QUERY_LENGTH} characters to search.</p>
          )}

          {status === 'loading' && products.length === 0 && <p className={styles.message}>Searching…</p>}

          {status === 'error' && (
            <p className={styles.message}>We couldn’t load results. Please try again.</p>
          )}

          {status === 'done' && products.length === 0 && (
            <p className={styles.message}>No products found for “{query}”.</p>
          )}

          {products.length > 0 && status !== 'idle' && status !== 'error' && (
            <>
              <p className={styles.meta}>
                {total} {total === 1 ? 'product' : 'products'} found
              </p>
              <ul className={`${styles.results} ${status === 'loading' ? styles.stale : ''}`}>
                {products.map(product => {
                  const image = product.images.find(img => img.is_primary) ?? product.images[0] ?? null;
                  return (
                    <li key={product.id}>
                      <Link href={productHref(product)} className={styles.result} onClick={onClose}>
                        <span className={styles.thumb}>
                          {image && (
                            <Image
                              src={mediaUrl(image.url)}
                              alt={image.alt_text ?? product.name}
                              fill
                              sizes="56px"
                              style={{ objectFit: 'cover', objectPosition: 'top center' }}
                            />
                          )}
                        </span>
                        <span className={styles.info}>
                          <span className={styles.name}>{product.name}</span>
                          <span className={styles.price}>
                            {formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY)}
                          </span>
                        </span>
                        {!product.in_stock && <span className={styles.soldOut}>Sold out</span>}
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </>
          )}
        </div>
      )}
    </>
  );
}
