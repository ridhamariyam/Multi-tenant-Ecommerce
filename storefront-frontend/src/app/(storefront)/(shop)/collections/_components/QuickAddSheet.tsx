'use client';

import Link from 'next/link';
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-toastify';

import { CloseIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useCart } from '@/context/CartContext';
import { catalogueApi } from '@/lib/api/catalogue';
import { optionValueLabel } from '@/lib/catalogue/size';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import type { ProductStorefront } from '@/types/catalogue';

import styles from './Collection.module.css';

interface Props {
  productId: string;
  productName: string;
  href: string;
  onClose: () => void;
}

/**
 * "Choose options" sheet that slides over the card image. The listing has no
 * variants, so the product is fetched when the sheet opens; Add to Bag stays
 * disabled until every option resolves to one in-stock variant, and only then
 * is a real `variant_id` handed to `CartContext`.
 */
export default function QuickAddSheet({ productId, productName, href, onClose }: Props) {
  const { addToCart, pending } = useCart();
  const [product, setProduct] = useState<ProductStorefront | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [selected, setSelected] = useState<Record<string, string>>({});
  const sheetRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    catalogueApi
      .getProduct(productId)
      .then(result => {
        if (cancelled) return;
        setProduct(result);
        // Options with a single value need no decision from the shopper.
        setSelected(
          Object.fromEntries(
            result.options.filter(option => option.values.length === 1).map(option => [option.name, option.values[0]]),
          ),
        );
      })
      .catch(() => {
        if (!cancelled) setLoadError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [productId]);

  useEffect(() => {
    sheetRef.current?.focus();
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose();
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  const variant = useMemo(() => {
    if (!product) return undefined;
    const inStock = product.variants.filter(v => v.in_stock);
    if (product.options.length === 0) return inStock.length === 1 ? inStock[0] : undefined;
    if (!product.options.every(option => selected[option.name])) return undefined;
    return inStock.find(v => product.options.every(option => v.options[option.name] === selected[option.name]));
  }, [product, selected]);

  function isAvailable(name: string, value: string) {
    return !!product?.variants.some(
      v =>
        v.in_stock &&
        v.options[name] === value &&
        Object.entries(selected).every(([key, chosen]) => key === name || v.options[key] === chosen),
    );
  }

  async function handleAdd() {
    if (!variant || pending) return;
    const failure = await addToCart(variant.id, 1);
    if (failure) {
      toast.error(failure);
      return;
    }
    onClose();
  }

  return (
    <div
      ref={sheetRef}
      className={styles.sheet}
      role="dialog"
      aria-label={`Choose options for ${productName}`}
      tabIndex={-1}
    >
      <div className={styles.sheetHead}>
        <span className={styles.sheetTitle}>{productName}</span>
        <button type="button" className={styles.sheetClose} onClick={onClose} aria-label="Close options">
          <CloseIcon size={16} />
        </button>
      </div>

      {loadError ? (
        <p className={styles.sheetNote}>Couldn&apos;t load options.</p>
      ) : !product ? (
        <p className={styles.sheetNote}>Loading options…</p>
      ) : (
        <>
          {product.options.map(option => (
            <div key={option.name} className={styles.sheetOption}>
              <span className={styles.sheetOptionLabel}>
                {option.name}
                {selected[option.name] ? `: ${optionValueLabel(option.name, selected[option.name])}` : ''}
              </span>
              <div className={styles.sheetValues}>
                {option.values.map(value => {
                  const active = selected[option.name] === value;
                  const available = isAvailable(option.name, value);
                  return (
                    <button
                      key={value}
                      type="button"
                      className={`${styles.sheetValue} ${active ? styles.sheetValueActive : ''}`}
                      aria-pressed={active}
                      disabled={!available}
                      onClick={() => setSelected(s => ({ ...s, [option.name]: value }))}
                    >
                      {optionValueLabel(option.name, value)}
                    </button>
                  );
                })}
              </div>
            </div>
          ))}

          <button
            type="button"
            className={styles.sheetAdd}
            disabled={!variant || pending}
            onClick={handleAdd}
          >
            {product.in_stock ? 'Add to Bag' : 'Sold Out'}
            {variant && <span>{formatMoney(variant.price, STOREFRONT_CURRENCY)}</span>}
          </button>
        </>
      )}

      <Link href={href} className={styles.sheetView}>
        View product details
      </Link>
    </div>
  );
}
