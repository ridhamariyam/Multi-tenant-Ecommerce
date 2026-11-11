'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useCallback, useState } from 'react';
import { toast } from 'react-toastify';

import { BagIcon, HeartIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useWishlist } from '@/context/WishlistContext';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatPriceRange } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import { formatMoney } from '@/lib/format';
import type { ProductSummaryStorefront } from '@/types/catalogue';
import type { WishlistItem } from '@/types/cart';

import styles from './Collection.module.css';
import QuickAddSheet from './QuickAddSheet';

interface Props {
  product: ProductSummaryStorefront;
  /** Real variant color names for this product, from the search endpoint. */
  colors: string[];
  priority?: boolean;
  /** Present on Wishlist: removes this saved variant and uses its saved price. */
  wishlistItem?: Pick<WishlistItem, 'id' | 'variant_name' | 'unit_price'>;
}

/**
 * Collection grid card: 3:4 image with status badge, wishlist heart and a
 * quick-add bag button; uppercase name, price, and color swatches that show
 * on hover (always shown on touch screens).
 *
 * Swatches paint each color name as a CSS color; the catalogue's option
 * values are plain color words, and an unrecognized one keeps the outlined
 * empty dot rather than an invented color.
 */
export default function CollectionCard({ product, colors, priority = false, wishlistItem }: Props) {
  const { isProductSaved, toggleProduct, removeItem, pending } = useWishlist();
  const [quickAddOpen, setQuickAddOpen] = useState(false);
  const closeQuickAdd = useCallback(() => setQuickAddOpen(false), []);

  const href = product.slug ? `/products/${encodeURIComponent(product.slug)}` : `/single-product/${product.id}`;
  const saved = isProductSaved(product.id);
  const price = wishlistItem
    ? formatMoney(String(wishlistItem.unit_price), STOREFRONT_CURRENCY)
    : formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY);

  async function handleToggleWishlist() {
    if (pending) return;
    const wasSaved = saved;
    const error = wishlistItem ? await removeItem(wishlistItem.id) : await toggleProduct(product.id);
    if (error) toast.error(error);
    else if (wasSaved) toast.info('Removed from your wishlist');
    else toast.success('Added to your wishlist');
  }

  const badge = !product.in_stock
    ? { label: 'Sold Out', dark: true }
    : product.on_sale
      ? { label: 'Sale', dark: false }
      : product.is_featured
        ? { label: 'Bestseller', dark: false }
        : null;

  return (
    <article className={styles.card}>
      <div className={styles.media}>
        <Link href={href} className={styles.mediaLink} tabIndex={-1} aria-hidden="true">
          {product.primary_image ? (
            <Image
              src={mediaUrl(product.primary_image.url)}
              alt={product.primary_image.alt_text ?? product.name}
              fill
              priority={priority}
              sizes="(max-width: 749px) 50vw, (max-width: 1024px) 33vw, 25vw"
              className={styles.image}
            />
          ) : (
            <span className={styles.mediaEmpty}>No image yet</span>
          )}
        </Link>

        {badge && <span className={`${styles.badge} ${badge.dark ? styles.badgeDark : ''}`}>{badge.label}</span>}

        <button
          type="button"
          className={`${styles.iconButton} ${styles.wishlistButton} ${saved ? styles.wishlistActive : ''}`}
          onClick={handleToggleWishlist}
          disabled={pending}
          aria-pressed={saved}
          aria-label={saved ? `Remove ${product.name} from wishlist` : `Save ${product.name} to wishlist`}
        >
          <HeartIcon size={15} filled={saved} />
        </button>

        {product.in_stock && (
          <button
            type="button"
            className={`${styles.iconButton} ${styles.quickAddButton}`}
            onClick={() => setQuickAddOpen(true)}
            aria-haspopup="dialog"
            aria-expanded={quickAddOpen}
            aria-label={`Add ${product.name} to bag`}
          >
            <BagIcon size={15} />
          </button>
        )}

        {quickAddOpen && (
          <QuickAddSheet productId={product.id} productName={product.name} href={href} onClose={closeQuickAdd} />
        )}
      </div>

      <div className={styles.info}>
        <h3 className={styles.name}>
          <Link href={href}>{product.name}</Link>
        </h3>
        {wishlistItem && <p className={styles.savedVariant}>{wishlistItem.variant_name}</p>}
        <div className={styles.cardPriceRow}>
          <p className={styles.price}>{price || 'Price on request'}</p>
          {colors.length > 0 && (
            <ul className={styles.swatches} aria-label="Available colors">
              {colors.slice(0, 5).map(color => (
                <li key={color} className={styles.swatch} style={{ backgroundColor: color.toLowerCase() }} title={color}>
                  <span className={styles.visuallyHidden}>{color}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </article>
  );
}
