'use client';

import Image from 'next/image';
import Link from 'next/link';
import { createPortal } from 'react-dom';
import { useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'react-toastify';

import { CloseIcon, MinusIcon, PlusIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useCart } from '@/context/CartContext';
import { getCartDrawerContent } from '@/lib/cart/actions';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney, formatPriceRange } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import type { CartItem } from '@/types/cart';
import type { ProductSummaryStorefront, VariantStorefront } from '@/types/catalogue';

import styles from './CartDrawer.module.css';

function ProductRow({
  item,
  variant,
  disabled,
  onQuantity,
  onRemove,
}: {
  item: CartItem;
  variant: VariantStorefront | null | undefined;
  disabled: boolean;
  onQuantity: (itemId: string, quantity: number) => void;
  onRemove: (itemId: string) => void;
}) {
  const options = variant ? Object.entries(variant.options) : [];
  const compareAt = Number(variant?.compare_at_price ?? 0);
  const unitPrice = Number(item.unit_price);
  const available = variant?.available_quantity;
  const canIncrease = typeof available === 'number' && item.quantity < available;

  return (
    <article className={styles.item}>
      <Link href={`/single-product/${item.product_id}`} className={styles.itemImage} aria-label={item.product_name}>
        {item.image ? (
          <Image
            src={mediaUrl(item.image.url)}
            alt={item.image.alt_text ?? item.product_name}
            fill
            sizes="82px"
          />
        ) : (
          <span className={styles.noImage}>CliQ.</span>
        )}
      </Link>

      <div className={styles.itemInfo}>
        <div className={styles.itemTop}>
          <Link href={`/single-product/${item.product_id}`} className={styles.itemName}>
            {item.product_name}
          </Link>
          <button
            type="button"
            className={styles.remove}
            disabled={disabled}
            aria-label={`Remove ${item.product_name} from cart`}
            onClick={() => onRemove(item.id)}
          >
            <CloseIcon size={16} />
          </button>
        </div>

        <p className={styles.itemVariant}>
          {options.length
            ? options.map(([name, value]) => `${name}: ${value}`).join(' · ')
            : item.variant_name}
        </p>

        <div className={styles.priceLine}>
          <span className={compareAt > unitPrice ? styles.salePrice : ''}>
            {formatMoney(item.unit_price, STOREFRONT_CURRENCY)}
          </span>
          {compareAt > unitPrice && <s>{formatMoney(String(compareAt), STOREFRONT_CURRENCY)}</s>}
          <span className={styles.lineSubtotal}>{formatMoney(item.subtotal, STOREFRONT_CURRENCY)}</span>
        </div>

        <div className={styles.itemBottom}>
          <div className={styles.quantity} aria-label={`Quantity ${item.quantity}`}>
            <button
              type="button"
              disabled={disabled || item.quantity <= 1}
              aria-label={`Decrease ${item.product_name} quantity`}
              onClick={() => onQuantity(item.id, item.quantity - 1)}
            >
              <MinusIcon size={13} />
            </button>
            <span aria-live="polite">{item.quantity}</span>
            <button
              type="button"
              disabled={disabled || !canIncrease}
              aria-label={`Increase ${item.product_name} quantity`}
              title={variant ? (canIncrease ? 'Increase quantity' : 'Maximum available quantity reached') : 'Checking availability'}
              onClick={() => onQuantity(item.id, item.quantity + 1)}
            >
              <PlusIcon size={13} />
            </button>
          </div>
          {typeof available === 'number' && available <= 5 && available > 0 && (
            <span className={styles.stockNote}>Only {available} available</span>
          )}
          {variant && !variant.in_stock && <span className={styles.stockNote}>Currently unavailable</span>}
        </div>
      </div>
    </article>
  );
}

function Recommendation({ product }: { product: ProductSummaryStorefront }) {
  const href = product.slug ? `/products/${encodeURIComponent(product.slug)}` : `/single-product/${product.id}`;
  return (
    <Link className={styles.recommendation} href={href}>
      <span className={styles.recommendationImage}>
        {product.primary_image ? (
          <Image
            src={mediaUrl(product.primary_image.url)}
            alt={product.primary_image.alt_text ?? product.name}
            fill
            sizes="72px"
          />
        ) : (
          <span className={styles.noImage}>CliQ.</span>
        )}
      </span>
      <span className={styles.recommendationCopy}>
        <span className={styles.recommendationName}>{product.name}</span>
        <span className={styles.recommendationPrice}>
          {formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY) || 'Price on request'}
        </span>
      </span>
      <span className={styles.recommendationArrow} aria-hidden="true">↗</span>
    </Link>
  );
}

export default function CartDrawer() {
  const {
    cart,
    items,
    pending,
    error,
    cartDrawerOpen,
    closeCartDrawer,
    updateQuantity,
    removeFromCart,
  } = useCart();
  const closeRef = useRef<HTMLButtonElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const [extras, setExtras] = useState<{
    recommendations: ProductSummaryStorefront[];
    variants: Record<string, VariantStorefront | null>;
  }>({ recommendations: [], variants: {} });

  const cartKey = useMemo(() => items.map(item => item.variant_id).sort().join(','), [items]);
  const productKey = useMemo(() => items.map(item => item.product_id).sort().join(','), [items]);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!cartDrawerOpen) return;
    let cancelled = false;
    const variantIds = cartKey ? cartKey.split(',') : [];
    const excludedProductIds = productKey ? productKey.split(',') : [];
    getCartDrawerContent(excludedProductIds, variantIds)
      .then(result => {
        if (!cancelled) setExtras(result);
      })
      .catch(() => {
        if (!cancelled) setExtras({ recommendations: [], variants: {} });
      });
    return () => {
      cancelled = true;
    };
  }, [cartDrawerOpen, cartKey, productKey]);

  useEffect(() => {
    if (!cartDrawerOpen) return;
    returnFocusRef.current = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const { overflow, paddingRight } = document.body.style;
    const scrollbarWidth = window.innerWidth - document.documentElement.clientWidth;
    document.body.style.overflow = 'hidden';
    if (scrollbarWidth > 0) document.body.style.paddingRight = `${scrollbarWidth}px`;
    closeRef.current?.focus();

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closeCartDrawer();
        return;
      }
      if (event.key !== 'Tab') return;
      const focusable = document.querySelectorAll<HTMLElement>(
        '[data-cart-drawer] a[href], [data-cart-drawer] button:not([disabled])',
      );
      if (!focusable.length) return;
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
      const target = returnFocusRef.current;
      if (target?.isConnected) target.focus();
      else document.querySelector<HTMLElement>('[data-cart-trigger]')?.focus();
    };
  }, [cartDrawerOpen, closeCartDrawer]);

  async function changeQuantity(itemId: string, quantity: number) {
    const failure = await updateQuantity(itemId, quantity);
    if (failure) toast.error(failure);
  }

  async function removeItem(itemId: string) {
    const failure = await removeFromCart(itemId);
    if (failure) toast.error(failure);
  }

  if (!mounted) return null;

  return createPortal(
    <div className={`${styles.root} ${cartDrawerOpen ? styles.open : ''}`} aria-hidden={!cartDrawerOpen} inert={!cartDrawerOpen}>
      <button type="button" className={styles.overlay} aria-label="Close cart" onClick={closeCartDrawer} tabIndex={cartDrawerOpen ? 0 : -1} />
      <aside
        className={styles.drawer}
        data-cart-drawer
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-drawer-title"
        aria-hidden={!cartDrawerOpen}
      >
        <header className={styles.header}>
          <div className={styles.heading}>
            <h2 id="cart-drawer-title">Your Cart</h2>
            <span aria-label={`${cart.item_count} items`}>{cart.item_count}</span>
          </div>
          <button ref={closeRef} type="button" className={styles.close} onClick={closeCartDrawer} aria-label="Close cart">
            <CloseIcon size={22} />
          </button>
        </header>

        <div className={styles.body}>
          {error && <p className={styles.error} role="alert">{error}</p>}
          {items.length === 0 ? (
            <div className={styles.empty}>
              <p>Your bag is currently empty.</p>
              <Link href="/products" className={styles.secondaryButton} onClick={closeCartDrawer}>Continue shopping</Link>
            </div>
          ) : (
            <div className={styles.items}>
              {items.map(item => (
                <ProductRow
                  key={item.id}
                  item={item}
                  variant={extras.variants[item.variant_id]}
                  disabled={pending}
                  onQuantity={changeQuantity}
                  onRemove={removeItem}
                />
              ))}
            </div>
          )}

          {extras.recommendations.length > 0 && (
            <section className={styles.recommendations} aria-labelledby="cart-recommendations-title">
              <h3 id="cart-recommendations-title">You May Also Like</h3>
              <div className={styles.recommendationList}>
                {extras.recommendations.map(product => <Recommendation key={product.id} product={product} />)}
              </div>
            </section>
          )}
        </div>

        <footer className={styles.footer}>
          <div className={styles.subtotal}>
            <span>Subtotal</span>
            <strong>{formatMoney(cart.subtotal, STOREFRONT_CURRENCY)}</strong>
          </div>
          <p className={styles.shippingNote}>Shipping calculated at checkout.</p>
          <div className={styles.actions}>
            <Link href="/cart" className={styles.viewCart} onClick={closeCartDrawer}>View Cart</Link>
            <Link
              href="/checkout"
              className={styles.checkout}
              aria-disabled={items.length === 0}
              onClick={event => {
                if (items.length === 0) event.preventDefault();
                else closeCartDrawer();
              }}
            >
              Checkout
            </Link>
          </div>
        </footer>
      </aside>
    </div>,
    document.body,
  );
}
