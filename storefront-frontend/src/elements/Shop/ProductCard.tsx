'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { toast } from 'react-toastify';

import { useWishlist } from '@/context/WishlistContext';
import { mediaUrl } from '@/lib/media';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatPriceRange } from '@/lib/format';
import type { ProductSummaryStorefront } from '@/types/catalogue';

import styles from './ProductCard.module.css';

interface ProductCardProps {
  product: ProductSummaryStorefront;
  rating?: number;
}

function HeartIcon({ filled }: { filled: boolean }) {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"
      fill={filled ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="1.6">
      <path d="M12 21s-7.5-4.6-10-9.1C.4 8.8 1.9 5.5 5.2 5.1c2-.3 3.6.8 4.4 2.1h.8c.8-1.3 2.4-2.4 4.4-2.1 3.3.4 4.8 3.7 3.2 6.8C19.5 16.4 12 21 12 21z" />
    </svg>
  );
}

function StarIcon({ variant }: { variant: 'full' | 'half' | 'empty' }) {
  const id = `half-${Math.random().toString(36).slice(2, 8)}`;
  const fill = variant === 'full' ? 'currentColor' : variant === 'empty' ? 'none' : `url(#${id})`;
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" className={variant === 'empty' ? styles.starEmpty : undefined}
      fill={fill} stroke="currentColor" strokeWidth="1" aria-hidden="true">
      {variant === 'half' && (
        <defs>
          <linearGradient id={id}>
            <stop offset="50%" stopColor="currentColor" />
            <stop offset="50%" stopColor="transparent" />
          </linearGradient>
        </defs>
      )}
      <path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z" />
    </svg>
  );
}

/**
 * A catalogue tile.
 *
 * The listing endpoint returns no variants, so there is nothing here to put
 * in a cart -- "Add to Cart" opens the product instead, where options are
 * chosen and a real variant id exists. Adding a guessed variant would be
 * the wrong item as often as the right one.
 */
export default function ProductCard({ product, rating = 0 }: ProductCardProps) {
  const router = useRouter();
  const { isProductSaved, toggleProduct, pending } = useWishlist();

  const href = product.slug
    ? `/products/${encodeURIComponent(product.slug)}`
    : `/single-product/${product.id}`;
  const image = product.primary_image;
  const saved = isProductSaved(product.id);

  async function handleToggleWishlist(event: React.MouseEvent) {
    event.preventDefault();
    if (pending) return;

    const wasSaved = saved;
    const error = await toggleProduct(product.id);

    if (error) toast.error(error);
    else if (wasSaved) toast.info('Removed from your wishlist');
    else toast.success('Added to your wishlist');
  }

  return (
    <div className={styles.card}>
      <button
        type="button"
        className={`${styles.wishlist} ${saved ? styles.active : ''}`}
        onClick={handleToggleWishlist}
        aria-label={saved ? 'Remove from wishlist' : 'Add to wishlist'}>
        <HeartIcon filled={saved} />
      </button>

      <Link href={href} className={styles.mediaLink}>
        <div className={styles.media}>
          {!product.in_stock && <div className={styles.soldOut}>Sold out</div>}
          {image && (
            <Image
              src={mediaUrl(image.url)}
              alt={image.alt_text ?? product.name}
              fill
              sizes="(max-width: 720px) 50vw, (max-width: 1080px) 33vw, 25vw"
              className={styles.img}
            />
          )}
          <div className={styles.overlay}>
            <span className={styles.viewBtn}>View Product</span>
          </div>
        </div>
      </Link>

      <div className={styles.body}>
        <p className={styles.name}>{product.name}</p>
        <p className={styles.price}>
          {formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY)}
        </p>
        <div className={styles.footer}>
          <span className={styles.rating}>
            {Array.from({ length: 5 }).map((_, index) => {
              const variant = index < Math.floor(rating) ? 'full' : index < rating ? 'half' : 'empty';
              return <StarIcon key={index} variant={variant} />;
            })}
          </span>
          <button type="button" className={styles.addBtn} onClick={() => router.push(href)}>
            {product.in_stock ? 'Add to Cart' : 'View'}
            <span className={styles.plus}>+</span>
          </button>
        </div>
      </div>
    </div>
  );
}
