'use client';

import Image from 'next/image';
import Link from 'next/link';
import { toast } from 'react-toastify';

import { BagIcon, HeartIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
import { useWishlist } from '@/context/WishlistContext';
import { mediaUrl } from '@/lib/media';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatPriceRange } from '@/lib/format';
import type { ProductSummaryStorefront } from '@/types/catalogue';

import listingStyles from './Listing.module.css';

interface Props {
  product: ProductSummaryStorefront;
  /** Real variant color names for this product (search endpoint), e.g. ["Red", "Black"]. */
  colors?: string[];
}

/**
 * A Product Listing card, styled to the reference design (badge, wishlist
 * heart over the image, name/price/swatches, an Add to Cart action that
 * only shows up to tablet width -- see `.addToCartBtn` in Listing.module.css).
 *
 * Swatches render each color name as its own CSS `background-color`. That
 * only works because the backend's color option values are ordinary color
 * words ("Red", "Black", ...), which are also valid CSS keywords -- nothing
 * is invented here, an unrecognized word just paints no swatch.
 *
 * The listing endpoint returns no variants, so there's no variant id to add
 * to the cart from here -- "Add to Cart" opens the product instead, same
 * reasoning as the older `elements/Shop/ProductCard`.
 */
export default function ProductCard({ product, colors = [] }: Props) {
  const { isProductSaved, toggleProduct, pending } = useWishlist();

  const href = `/single-product/${product.id}`;
  const saved = isProductSaved(product.id);

  async function handleToggleWishlist(event: React.MouseEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (pending) return;

    const wasSaved = saved;
    const error = await toggleProduct(product.id);

    if (error) toast.error(error);
    else if (wasSaved) toast.info('Removed from your wishlist');
    else toast.success('Saved to your wishlist');
  }

  return (
    <div className={listingStyles.card}>
      <div className={listingStyles.cardMediaWrap}>
        <Link href={href} className={listingStyles.cardMediaLink} aria-label={product.name}>
          <div className={listingStyles.cardMedia}>
            {!product.in_stock ? (
              <span className={`${listingStyles.badge} ${listingStyles.badgeDark}`}>Sold Out</span>
            ) : product.is_featured ? (
              <span className={listingStyles.badge}>Bestseller</span>
            ) : null}

            {product.primary_image ? (
              <Image
                src={mediaUrl(product.primary_image.url)}
                alt={product.primary_image.alt_text ?? product.name}
                fill
                sizes="(max-width: 640px) 50vw, (max-width: 1024px) 33vw, 25vw"
                className={listingStyles.cardImg}
              />
            ) : (
              <div className={listingStyles.mediaEmpty}>No image yet</div>
            )}
          </div>
        </Link>

        <button
          type="button"
          className={`${listingStyles.wishlistBtn} ${saved ? listingStyles.wishlistBtnActive : ''}`}
          onClick={handleToggleWishlist}
          disabled={pending}
          aria-pressed={saved}
          aria-label={saved ? 'Remove from wishlist' : 'Save to wishlist'}
        >
          <HeartIcon size={16} filled={saved} />
        </button>
      </div>

      <Link href={href} className={listingStyles.cardBody}>
        <p className={listingStyles.name}>{product.name}</p>
        <p className={listingStyles.price}>
          {formatPriceRange(product.price_from, product.price_to, STOREFRONT_CURRENCY) || 'Price on request'}
        </p>
        {/* Rendered even with zero colors -- see .swatchRow in Listing.module.css --
            so a product with no color options doesn't sit shorter than its
            neighbors and throw the row's price/button alignment off. */}
        <div className={listingStyles.swatchRow}>
          {colors.slice(0, 5).map(color => (
            <span
              key={color}
              className={listingStyles.swatch}
              style={{ backgroundColor: color.toLowerCase() }}
              title={color}
            />
          ))}
        </div>
      </Link>

      <Link href={href} className={listingStyles.addToCartBtn}>
        <BagIcon size={14} />
        {product.in_stock ? 'Add to Cart' : 'View Product'}
      </Link>
    </div>
  );
}
