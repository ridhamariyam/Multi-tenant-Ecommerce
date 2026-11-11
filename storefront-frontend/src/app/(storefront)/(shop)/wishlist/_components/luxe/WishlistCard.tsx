'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useEffect, useState } from 'react';
import { toast } from 'react-toastify';

import {
  BagIcon,
  HeartIcon,
  StarIcon,
} from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import listingStyles from '@/components/luxe/Listing.module.css';
import { useWishlist } from '@/context/WishlistContext';
import { mediaUrl } from '@/lib/media';
import { reviewApi } from '@/lib/api/reviews';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import type { WishlistItem } from '@/types/cart';
import type { RatingSummary } from '@/types/reviews';

import AddToBagModal from './AddToBagModal';
import wishlistStyles from './Wishlist.module.css';

interface Props {
  item: WishlistItem;
}

/**
 * Wishlist product card using the existing Product Listing styles,
 * with wishlist-specific rating and Add to Bag functionality.
 */
export default function WishlistCard({ item }: Props) {
  const { removeItem, pending: wishlistPending } = useWishlist();

  const [rating, setRating] = useState<RatingSummary | null>(null);
  const [bagModalOpen, setBagModalOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    reviewApi
      .summary(item.product_id)
      .then(summary => {
        if (!cancelled) {
          setRating(summary);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRating(null);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [item.product_id]);

  const href = `/single-product/${item.product_id}`;

  async function handleRemove() {
    const error = await removeItem(item.id);

    if (error) {
      toast.error(error);
    } else {
      toast.info('Removed from your wishlist');
    }
  }


  return (
    <div className={wishlistStyles.card}>
      <div className={listingStyles.cardMediaWrap}>
        <Link
          href={href}
          className={listingStyles.cardMediaLink}
          aria-label={item.product_name}
        >
          <div
            className={`${listingStyles.cardMedia} ${wishlistStyles.media}`}
          >
            {item.image ? (
              <Image
                src={mediaUrl(item.image.url)}
                alt={item.image.alt_text ?? item.product_name}
                fill
                sizes="(max-width: 639px) 50vw, (max-width: 1023px) 50vw, (max-width: 1439px) 33vw, 25vw"
                className={listingStyles.cardImg}
              />
            ) : (
              <div className={listingStyles.mediaEmpty}>No image yet</div>
            )}
          </div>
        </Link>

        <button
          type="button"
          className={`${listingStyles.wishlistBtn} ${listingStyles.wishlistBtnActive}`}
          onClick={handleRemove}
          disabled={wishlistPending}
          aria-pressed="true"
          aria-label="Remove from wishlist"
        >
          <HeartIcon size={16} filled />
        </button>
      </div>

      <Link href={href} className={wishlistStyles.cardBody}>
        <p className={listingStyles.name}>{item.product_name}</p>

        {item.variant_name && (
          <p className={wishlistStyles.variant}>{item.variant_name}</p>
        )}

        <p className={listingStyles.price}>
          {formatMoney(String(item.unit_price), STOREFRONT_CURRENCY)}
        </p>
      </Link>

      {rating && rating.total_reviews > 0 && (
        <p className={wishlistStyles.rating}>
          <StarIcon size={13} />
          {rating.average_rating.toFixed(1)}
          <span className={wishlistStyles.ratingCount}>
            ({rating.total_reviews})
          </span>
        </p>
      )}

      <button
        type="button"
        className={wishlistStyles.addToBagBtn}
        onClick={() => setBagModalOpen(true)}
      >
        <BagIcon size={14} />
        Add to Cart
      </button>

      {bagModalOpen && <AddToBagModal item={item} onClose={() => setBagModalOpen(false)} />}
    </div>
  );
}
