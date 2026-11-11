'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { ChevronDownIcon, CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';

import styles from './Collection.module.css';
import FilterDrawer, { type CategoryOption } from './FilterDrawer';
import {
  COLLECTION_SORTS,
  type CollectionFilters,
  type CollectionSort,
  EMPTY_FILTERS,
  activeFilterCount,
  collectionQuery,
} from './collectionQuery';

interface Props {
  basePath: string;
  sort: CollectionSort;
  filters: CollectionFilters;
  shown: number;
  total: number;
  categories: CategoryOption[];
  colorOptions: string[];
  sizeOptions: string[];
  priceBounds: { min: number; max: number } | null;
}

/**
 * Filters button (opens the drawer), "Showing X of Y products", the sort
 * dropdown, and a row of removable chips for whatever filters are applied.
 * Every change is a navigation, so the server route re-filters the grid and
 * the state survives refresh, back/forward and sharing.
 */
export default function CollectionToolbar({
  basePath,
  sort,
  filters,
  shown,
  total,
  categories,
  colorOptions,
  sizeOptions,
  priceBounds,
}: Props) {
  const router = useRouter();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [sortOpen, setSortOpen] = useState(false);
  const sortRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!sortOpen) return;
    function onPointerDown(event: MouseEvent) {
      if (sortRef.current && !sortRef.current.contains(event.target as Node)) setSortOpen(false);
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setSortOpen(false);
    }
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [sortOpen]);

  function go(nextSort: CollectionSort, nextFilters: CollectionFilters) {
    router.push(`${basePath}${collectionQuery(nextSort, nextFilters)}`, { scroll: false });
  }

  const activeSort = COLLECTION_SORTS.find(option => option.value === sort) ?? COLLECTION_SORTS[0];
  const filterCount = activeFilterCount(filters);

  const chips: { key: string; label: string; next: CollectionFilters }[] = [
    ...(filters.minPrice || filters.maxPrice
      ? [
          {
            key: 'price',
            label: `${filters.minPrice ? formatMoney(filters.minPrice, STOREFRONT_CURRENCY) : 'Any'} – ${
              filters.maxPrice ? formatMoney(filters.maxPrice, STOREFRONT_CURRENCY) : 'Any'
            }`,
            next: { ...filters, minPrice: '', maxPrice: '' },
          },
        ]
      : []),
    ...filters.colors.map(value => ({
      key: `c-${value}`,
      label: value,
      next: { ...filters, colors: filters.colors.filter(v => v !== value) },
    })),
    ...filters.sizes.map(value => ({
      key: `s-${value}`,
      label: `Size ${value}`,
      next: { ...filters, sizes: filters.sizes.filter(v => v !== value) },
    })),
  ];

  return (
    <>
      <div className={styles.toolbar}>
        <button
          type="button"
          className={styles.toolbarButton}
          aria-haspopup="dialog"
          aria-expanded={drawerOpen}
          onClick={() => setDrawerOpen(true)}
        >
          Filters
          {filterCount > 0 && <span className={styles.countBadge}>{filterCount}</span>}
          <ChevronDownIcon size={12} />
        </button>

        <p className={styles.showing} role="status" aria-live="polite">
          <span className={styles.showingLabel}>Showing</span>
          <span className={styles.showingValue}>
            {shown} of {total} product{total === 1 ? '' : 's'}
          </span>
        </p>

        <div className={styles.sortWrap} ref={sortRef}>
          <button
            type="button"
            className={styles.toolbarButton}
            aria-haspopup="listbox"
            aria-expanded={sortOpen}
            aria-label={`Sort by: ${activeSort.label}`}
            onClick={() => setSortOpen(open => !open)}
          >
            {activeSort.label}
            <ChevronDownIcon size={12} className={sortOpen ? styles.chevronUp : undefined} />
          </button>
          {sortOpen && (
            <div className={styles.sortPanel} role="listbox" aria-label="Sort products">
              {COLLECTION_SORTS.map(option => (
                <button
                  key={option.value}
                  type="button"
                  role="option"
                  aria-selected={option.value === sort}
                  className={`${styles.sortOption} ${option.value === sort ? styles.sortOptionActive : ''}`}
                  onClick={() => {
                    setSortOpen(false);
                    if (option.value !== sort) go(option.value, filters);
                  }}
                >
                  {option.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {chips.length > 0 && (
        <div className={styles.chips}>
          {chips.map(chip => (
            <button
              key={chip.key}
              type="button"
              className={styles.chip}
              onClick={() => go(sort, chip.next)}
              aria-label={`Remove filter ${chip.label}`}
            >
              {chip.label}
              <CloseIcon size={12} />
            </button>
          ))}
          <button type="button" className={styles.chipClear} onClick={() => go(sort, EMPTY_FILTERS)}>
            Clear all
          </button>
        </div>
      )}

      <FilterDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        filters={filters}
        onApply={next => {
          setDrawerOpen(false);
          go(sort, next);
        }}
        categories={categories}
        colorOptions={colorOptions}
        sizeOptions={sizeOptions}
        priceBounds={priceBounds}
      />
    </>
  );
}
