'use client';

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import { CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import type { SizeChart } from '@/types/catalogue';

import styles from './ProductDetails.module.css';

interface Props {
  chart: SizeChart;
  productName: string;
  /** Sizes this product can currently be bought in; other columns are struck through. */
  availableSizes: string[];
  selectedSize: string | undefined;
  onSelectSize: (size: string) => void;
  onClose: () => void;
}

/**
 * The product's own size chart, read back by the API in both inches and
 * centimetres. Clicking a size column picks it; "Select size" applies the
 * pick to the product form and closes the guide.
 */
export default function SizeGuideModal({
  chart,
  productName,
  availableSizes,
  selectedSize,
  onSelectSize,
  onClose,
}: Props) {
  const [unit, setUnit] = useState<'in' | 'cm'>(chart.unit);
  const [picked, setPicked] = useState<string | undefined>(selectedSize);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    closeRef.current?.focus();
    const { overflow } = document.body.style;
    document.body.style.overflow = 'hidden';
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  const sellable = (size: string) => availableSizes.includes(size);

  // Portalled to <body> so the sticky details column can't stack above it.
  return createPortal(
    <div className={styles.modalRoot}>
      <div className={styles.modalOverlay} onClick={onClose} />
      <div className={styles.modal} role="dialog" aria-modal="true" aria-labelledby="size-guide-title">
        <button ref={closeRef} type="button" className={styles.modalClose} onClick={onClose} aria-label="Close size guide">
          <CloseIcon size={20} />
        </button>

        <h2 id="size-guide-title" className={styles.modalTitle}>
          Size Guide
        </h2>

        <div className={styles.unitToggle} role="radiogroup" aria-label="Units">
          {(['in', 'cm'] as const).map(value => (
            <label key={value} className={styles.unitOption}>
              <input
                type="radio"
                name="size-guide-unit"
                checked={unit === value}
                onChange={() => setUnit(value)}
              />
              {value === 'in' ? 'Inch' : 'Cm'}
            </label>
          ))}
        </div>

        <p className={styles.chartTitle}>{productName} sizing</p>

        <div className={styles.tableScroll}>
          <table className={styles.chart}>
            <thead>
              <tr>
                <th scope="col" className={styles.chartCorner}>
                  Measurement
                </th>
                {chart.rows.map(row => (
                  <th
                    key={row.size}
                    scope="col"
                    className={`${styles.chartSize} ${picked === row.size ? styles.chartPicked : ''} ${
                      sellable(row.size) ? '' : styles.chartUnavailable
                    }`}
                  >
                    <button
                      type="button"
                      onClick={() => setPicked(row.size)}
                      disabled={!sellable(row.size)}
                      aria-pressed={picked === row.size}
                    >
                      {row.size}
                    </button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {chart.measurements.map(measurement => (
                <tr key={measurement}>
                  <th scope="row">{measurement}</th>
                  {chart.rows.map(row => {
                    const value = (unit === 'in' ? row.values_in : row.values_cm)[measurement];
                    return (
                      <td
                        key={row.size}
                        className={`${picked === row.size ? styles.chartPicked : ''} ${
                          sellable(row.size) ? '' : styles.chartUnavailable
                        }`}
                      >
                        {value ?? '—'}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <button
          type="button"
          className={styles.modalSelect}
          disabled={!picked}
          onClick={() => {
            if (picked) onSelectSize(picked);
            onClose();
          }}
        >
          {picked ? `Select size ${picked}` : 'Select size'}
        </button>

        {chart.note && (
          <p className={styles.chartNote}>
            <strong>Fit note:</strong> {chart.note}
          </p>
        )}
      </div>
    </div>,
    document.body,
  );
}
