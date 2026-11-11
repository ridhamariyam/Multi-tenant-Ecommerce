'use client';

import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import type { ProductSort } from '@/types/catalogue';

import { ChevronDownIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';

import { SlidersIcon } from './Icons';
import listingStyles from './Listing.module.css';

/**
 * Sort values the Product Listing URL accepts. `newest`/`price_low`/
 * `price_high` map straight onto the primary listing endpoint's real
 * `ProductSort`. `rating_desc`/`popularity` only exist on the search
 * endpoint (rating client-sorted there since the backend has no rating
 * ORDER BY; popularity is its real `RECOMMENDED` sort) -- see page.tsx's
 * `usesVariantData`/`toSearchSort`.
 */
export type ListingSort = ProductSort | 'rating_desc' | 'popularity';

const SORT_OPTIONS: { value: ListingSort; label: string }[] = [
  { value: 'newest', label: 'Newest' },
  { value: 'price_low', label: 'Price: Low to High' },
  { value: 'price_high', label: 'Price: High to Low' },
  { value: 'rating_desc', label: 'Rating: High to Low' },
  { value: 'popularity', label: 'Popularity' },
];

interface Props {
  sort: ListingSort;
  minPrice: string;
  maxPrice: string;
  color: string;
  colors: string[];
  size: string;
  sizes: string[];
}

/**
 * Two consolidated dropdowns -- Sort and Filter -- covering every real
 * product-discovery param the backend supports, split across
 * `/storefront/products` (category chips stay server-rendered links; see
 * page.tsx) and `/storefront/search-products` (rating/popularity sort,
 * color/size filter). No search input here -- `q` is still a real,
 * deep-linkable `/shop-list?q=...` param the backend honors, just not
 * exposed as a visible control on this page.
 *
 * Color and Size stay visible even when their option list is empty: the
 * catalogue currently has no populated variants, but the filter itself is
 * real backend functionality, not something to hide until the data catches
 * up.
 */
export default function ListingControls({
  sort,
  minPrice,
  maxPrice,
  color,
  colors,
  size,
  sizes,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [min, setMin] = useState(minPrice);
  const [max, setMax] = useState(maxPrice);
  const [sortOpen, setSortOpen] = useState(false);
  const [filterOpen, setFilterOpen] = useState(false);
  const sortRef = useRef<HTMLDivElement>(null);
  const filterRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (sortRef.current && !sortRef.current.contains(event.target as Node)) setSortOpen(false);
      if (filterRef.current && !filterRef.current.contains(event.target as Node)) setFilterOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  // Keep the local price inputs in sync when navigation changes them from
  // outside this component (Clear filters, browser back/forward).
  useEffect(() => {
    setMin(minPrice);
    setMax(maxPrice);
  }, [minPrice, maxPrice]);

  function navigate(next: Record<string, string | null>) {
    const params = new URLSearchParams(searchParams.toString());
    for (const [key, value] of Object.entries(next)) {
      if (value) params.set(key, value);
      else params.delete(key);
    }
    params.delete('page');
    router.push(`${pathname}?${params.toString()}`);
  }

  const activeSort = SORT_OPTIONS.find(opt => opt.value === sort) ?? SORT_OPTIONS[0];
  const filterCount = (minPrice || maxPrice ? 1 : 0) + (color ? 1 : 0) + (size ? 1 : 0);

  return (
    <div className={listingStyles.controls}>
      <div className={listingStyles.dropdownWrap} ref={sortRef}>
        <button
          type="button"
          className={listingStyles.dropdownTrigger}
          aria-haspopup="listbox"
          aria-expanded={sortOpen}
          onClick={() => {
            setSortOpen(v => !v);
            setFilterOpen(false);
          }}
        >
          Sort by: {activeSort.label}
          <ChevronDownIcon size={12} />
        </button>
        {sortOpen && (
          <div className={listingStyles.dropdownPanel} role="listbox">
            {SORT_OPTIONS.map(opt => (
              <button
                key={opt.value}
                type="button"
                role="option"
                aria-selected={opt.value === sort}
                className={`${listingStyles.dropdownOption} ${opt.value === sort ? listingStyles.dropdownOptionActive : ''}`}
                onClick={() => {
                  navigate({ sort: opt.value === 'newest' ? null : opt.value });
                  setSortOpen(false);
                }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className={listingStyles.dropdownWrap} ref={filterRef}>
        <button
          type="button"
          className={listingStyles.dropdownTrigger}
          aria-haspopup="dialog"
          aria-expanded={filterOpen}
          onClick={() => {
            setFilterOpen(v => !v);
            setSortOpen(false);
          }}
        >
          <SlidersIcon size={14} />
          Filter
          {filterCount > 0 && <span className={listingStyles.filterBadge}>{filterCount}</span>}
        </button>
        {filterOpen && (
          <div className={`${listingStyles.dropdownPanel} ${listingStyles.filterPanel}`} role="dialog" aria-label="Filter products">
            <div className={listingStyles.filterGroup}>
              <span className={listingStyles.filterLabel}>Price</span>
              <div className={listingStyles.priceRow}>
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={min}
                  onChange={e => setMin(e.target.value)}
                  placeholder="Min"
                  className={listingStyles.priceInput}
                  aria-label="Minimum price"
                />
                <span className={listingStyles.priceDash}>–</span>
                <input
                  type="number"
                  inputMode="decimal"
                  min={0}
                  step="0.01"
                  value={max}
                  onChange={e => setMax(e.target.value)}
                  placeholder="Max"
                  className={listingStyles.priceInput}
                  aria-label="Maximum price"
                />
              </div>
            </div>

            <div className={listingStyles.filterGroup}>
              <span className={listingStyles.filterLabel}>Color</span>
              {colors.length > 0 ? (
                <select
                  className={listingStyles.filterSelect}
                  value={color}
                  onChange={e => navigate({ color: e.target.value || null })}
                  aria-label="Filter by color"
                >
                  <option value="">All Colors</option>
                  {colors.map(c => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              ) : (
                <p className={listingStyles.filterEmptyNote}>No colors available yet</p>
              )}
            </div>

            <div className={listingStyles.filterGroup}>
              <span className={listingStyles.filterLabel}>Size</span>
              {sizes.length > 0 ? (
                <select
                  className={listingStyles.filterSelect}
                  value={size}
                  onChange={e => navigate({ product_size: e.target.value || null })}
                  aria-label="Filter by size"
                >
                  <option value="">All Sizes</option>
                  {sizes.map(s => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              ) : (
                <p className={listingStyles.filterEmptyNote}>No sizes available yet</p>
              )}
            </div>

            <div className={listingStyles.filterActions}>
              <button
                type="button"
                className={listingStyles.filterClear}
                onClick={() => {
                  setMin('');
                  setMax('');
                  navigate({ min_price: null, max_price: null, color: null, product_size: null });
                }}
              >
                Clear
              </button>
              <button
                type="button"
                className={listingStyles.filterApply}
                onClick={() => {
                  navigate({ min_price: min.trim() || null, max_price: max.trim() || null });
                  setFilterOpen(false);
                }}
              >
                Apply
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
