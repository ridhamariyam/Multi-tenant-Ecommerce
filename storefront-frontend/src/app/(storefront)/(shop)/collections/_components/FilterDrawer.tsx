'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';

import { ChevronDownIcon, CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';

import styles from './Collection.module.css';
import { type CollectionFilters, EMPTY_FILTERS } from './collectionQuery';

export interface CategoryOption {
  name: string;
  href: string;
  count: number;
  active: boolean;
}

interface Props {
  open: boolean;
  onClose: () => void;
  filters: CollectionFilters;
  onApply: (filters: CollectionFilters) => void;
  categories: CategoryOption[];
  colorOptions: string[];
  sizeOptions: string[];
  priceBounds: { min: number; max: number } | null;
}

/** Currency symbol for the price inputs' prefix, e.g. "₹". */
const CURRENCY_SYMBOL =
  new Intl.NumberFormat('en-IN', { style: 'currency', currency: process.env.NEXT_PUBLIC_CURRENCY ?? 'INR' })
    .formatToParts(0)
    .find(part => part.type === 'currency')?.value ?? '';

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter(item => item !== value) : [...list, value];
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <details className={styles.facet} open>
      <summary className={styles.facetSummary}>
        {title}
        <ChevronDownIcon size={14} className={styles.facetChevron} />
      </summary>
      <div className={styles.facetBody}>{children}</div>
    </details>
  );
}

/**
 * Centered filter modal. Selections are staged locally and only
 * applied with Apply filters; Clear all resets the staged selection. Category
 * is a set of links to the sibling collections, so it navigates immediately.
 * Color and Size only appear when the catalogue's variants actually carry them.
 */
export default function FilterDrawer({
  open,
  onClose,
  filters,
  onApply,
  categories,
  colorOptions,
  sizeOptions,
  priceBounds,
}: Props) {
  const [draft, setDraft] = useState<CollectionFilters>(filters);
  const closeRef = useRef<HTMLButtonElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  // Re-stage from the URL each time the modal opens.
  useEffect(() => {
    if (open) setDraft(filters);
  }, [open, filters]);

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    closeRef.current?.focus();
    // Lock page scroll; pad by the scrollbar's width so the page doesn't shift.
    const { overflow, paddingRight } = document.body.style;
    const scrollbar = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = 'hidden';
    if (scrollbar > 0) document.body.style.paddingRight = `${scrollbar}px`;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        onClose();
        return;
      }
      if (event.key !== 'Tab') return;

      const focusable = dialogRef.current?.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), input:not([disabled]), summary, [tabindex]:not([tabindex="-1"])',
      );
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.body.style.paddingRight = paddingRight;
      document.removeEventListener('keydown', onKeyDown);
      returnFocusRef.current?.focus();
    };
  }, [open, onClose]);

  return (
    <div className={`${styles.drawerRoot} ${open ? styles.drawerOpen : ''}`} aria-hidden={!open} inert={!open}>
      <div
        className={styles.drawerOverlay}
        onClick={event => {
          if (event.target === event.currentTarget) onClose();
        }}
      />
      <div
        ref={dialogRef}
        className={styles.drawer}
        role="dialog"
        aria-modal="true"
        aria-labelledby="collection-filter-title"
        aria-describedby="collection-filter-description"
        tabIndex={-1}
      >
        <div className={styles.drawerHead}>
          <button ref={closeRef} type="button" className={styles.drawerClose} onClick={onClose} aria-label="Close filters">
            <CloseIcon size={20} />
          </button>
          <div>
            <h2 id="collection-filter-title" className={styles.drawerTitle}>
              Filter &amp; Sort
            </h2>
            <p id="collection-filter-description" className={styles.drawerDescription}>
              Refine the edit to find your perfect piece.
            </p>
          </div>
        </div>

        <form
          className={styles.drawerForm}
          onSubmit={event => {
            event.preventDefault();
            onApply(draft);
          }}
        >
          <div className={styles.drawerBody}>
            {categories.length > 1 && (
              <Section title="Category">
                <ul className={styles.categoryList}>
                  {categories.map(category => (
                    <li key={category.href}>
                      <Link
                        href={category.href}
                        className={`${styles.optionRow} ${category.active ? styles.optionRowActive : ''}`}
                        aria-current={category.active ? 'page' : undefined}
                        onClick={onClose}
                      >
                        <span className={styles.radio} aria-hidden="true" />
                        {category.name}
                        <span className={styles.optionCount}>({category.count})</span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </Section>
            )}

            {sizeOptions.length > 0 && (
              <Section title="Size">
                <div className={styles.sizeGrid}>
                  {sizeOptions.map(size => {
                    const checked = draft.sizes.includes(size);
                    return (
                      <label key={size} className={`${styles.sizeChip} ${checked ? styles.sizeChipActive : ''}`}>
                        <input
                          type="checkbox"
                          className={styles.visuallyHidden}
                          checked={checked}
                          onChange={() => setDraft(d => ({ ...d, sizes: toggle(d.sizes, size) }))}
                        />
                        {size}
                      </label>
                    );
                  })}
                </div>
              </Section>
            )}

            {colorOptions.length > 0 && (
              <Section title="Color">
                {colorOptions.map(color => (
                  <label key={color} className={styles.optionRow}>
                    <input
                      type="checkbox"
                      className={styles.checkbox}
                      checked={draft.colors.includes(color)}
                      onChange={() => setDraft(d => ({ ...d, colors: toggle(d.colors, color) }))}
                    />
                    <span className={styles.colorDot} style={{ backgroundColor: color.toLowerCase() }} aria-hidden="true" />
                    {color}
                  </label>
                ))}
              </Section>
            )}

            <Section title="Price">
              <div className={styles.priceRow}>
                <label className={styles.priceField}>
                  <span className={styles.priceLabel}>From</span>
                  <span className={styles.priceInputWrap}>
                    <span aria-hidden="true">{CURRENCY_SYMBOL}</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      value={draft.minPrice}
                      placeholder={priceBounds ? String(priceBounds.min) : '0'}
                      onChange={event => setDraft(d => ({ ...d, minPrice: event.target.value }))}
                    />
                  </span>
                </label>
                <label className={styles.priceField}>
                  <span className={styles.priceLabel}>To</span>
                  <span className={styles.priceInputWrap}>
                    <span aria-hidden="true">{CURRENCY_SYMBOL}</span>
                    <input
                      type="number"
                      inputMode="decimal"
                      min={0}
                      value={draft.maxPrice}
                      placeholder={priceBounds ? String(priceBounds.max) : ''}
                      onChange={event => setDraft(d => ({ ...d, maxPrice: event.target.value }))}
                    />
                  </span>
                </label>
              </div>
            </Section>
          </div>

          <div className={styles.drawerActions}>
            <button type="button" className={styles.outlineButton} onClick={() => setDraft(EMPTY_FILTERS)}>
              Clear all
            </button>
            <button type="submit" className={styles.solidButton}>
              Apply filters
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
