'use client';

import Image from 'next/image';
import Link from 'next/link';
import { toast } from 'react-toastify';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { BagIcon } from '@/app/(storefront)/(home)/home/_components/luxe/Icons';
// Reused from the Product Listing page -- same breadcrumb/heading banner
// every luxe page opens with (see ShopWishList for the identical pattern).
import listingStyles from '@/app/(storefront)/(shop)/shop-list/_components/luxe/Listing.module.css';
import MobileBottomNav from '@/components/MobileBottomNav';
import { useCart, useRefreshOnCartChange } from '@/context/CartContext';
import { mediaUrl } from '@/lib/media';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import type { CartItem } from '@/types/cart';
import type { CheckoutPreview } from '@/types/orders';

import styles from './Cart.module.css';

// -----------------------------------
// ROW
// -----------------------------------

function QtyStepper({
  item,
  disabled,
  onQtyChange,
}: {
  item: CartItem;
  disabled: boolean;
  onQtyChange: (itemId: string, quantity: number) => void;
}) {
  return (
    <div className={styles.qtyStepper}>
      <button
        type="button"
        disabled={disabled || item.quantity <= 1}
        onClick={() => onQtyChange(item.id, item.quantity - 1)}
        aria-label="Decrease quantity">
        −
      </button>
      <span>{item.quantity}</span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onQtyChange(item.id, item.quantity + 1)}
        aria-label="Increase quantity">
        +
      </button>
    </div>
  );
}

function RemoveButton({
  item,
  disabled,
  onRemove,
}: {
  item: CartItem;
  disabled: boolean;
  onRemove: (itemId: string) => void;
}) {
  return (
    <button
      type="button"
      className={styles.removeBtn}
      disabled={disabled}
      onClick={() => onRemove(item.id)}
      aria-label={`Remove ${item.product_name} from cart`}>
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
        <path d="M5 5l14 14M19 5 5 19" strokeLinecap="round" />
      </svg>
    </button>
  );
}

/**
 * Below `md` this renders as a stacked row: image, then name/variant/price/
 * qty stacked underneath with the remove "X" at top right. At `md` and up
 * it switches to a single row -- image, name/variant/price, then quantity,
 * line total and remove lined up on the right -- so `.desktopMeta`
 * duplicates the qty stepper and remove button for that row (CSS shows
 * exactly one copy of each at a time; see Cart.module.css) rather than
 * reflowing the same nodes, which CSS alone can't do across a breakpoint
 * that also regroups the surrounding markup.
 *
 * The image box uses `object-fit: contain` rather than the Product Listing
 * grid's `cover` crop -- a cart line is the shopper's own chosen item, not
 * a browsing tile, so the whole photo stays visible instead of being cropped
 * to fill a fixed box.
 */
function CartRow({
  item,
  disabled,
  onQtyChange,
  onRemove,
}: {
  item: CartItem;
  disabled: boolean;
  onQtyChange: (itemId: string, quantity: number) => void;
  onRemove: (itemId: string) => void;
}) {
  return (
    <div className={styles.row}>
      <Link href={`/single-product/${item.product_id}`} className={styles.thumb} aria-label={item.product_name}>
        {item.image ? (
          <Image
            src={mediaUrl(item.image.url)}
            alt={item.image.alt_text ?? item.product_name}
            fill
            sizes="(min-width: 992px) 140px, 110px"
          />
        ) : (
          <div className={styles.thumbEmpty}>No image yet</div>
        )}
      </Link>

      <div className={styles.info}>
        <div className={styles.infoTop}>
          <div>
            <p className={styles.name}>
              <Link href={`/single-product/${item.product_id}`}>{item.product_name}</Link>
            </p>
            <p className={styles.variant}>{item.variant_name}</p>
          </div>

          <div className={styles.removeBtnMobile}>
            <RemoveButton item={item} disabled={disabled} onRemove={onRemove} />
          </div>
        </div>

        <p className={styles.price}>{formatMoney(item.unit_price, STOREFRONT_CURRENCY)}</p>

        <div className={styles.qtyStepperMobile}>
          <QtyStepper item={item} disabled={disabled} onQtyChange={onQtyChange} />
        </div>
      </div>

      <div className={styles.desktopMeta}>
        <QtyStepper item={item} disabled={disabled} onQtyChange={onQtyChange} />
        <p className={styles.lineTotal}>{formatMoney(item.subtotal, STOREFRONT_CURRENCY)}</p>
        <RemoveButton item={item} disabled={disabled} onRemove={onRemove} />
      </div>
    </div>
  );
}

// -----------------------------------
// CART
// -----------------------------------

/**
 * The cart page.
 *
 * All data comes from CartContext, the same real, backend-held cart the
 * header badge and every "Add to Cart" button already use -- there is no
 * separate fetch or mock data here. Restyled to the same CliQ design system
 * as Home/Product Listing/Wishlist (their shared header/footer/mobile nav,
 * `Home.module.css` tokens and the Listing page's banner/breadcrumb), not
 * just a visual approximation of it.
 */
export default function Cart({ preview: serverPreview }: { preview: CheckoutPreview | null }) {
  const { cart, items, pending, error, updateQuantity, removeFromCart, clearCart } = useCart();
  const refreshing = useRefreshOnCartChange();
  // The server's preview (discount, shipping, tax, total) is priced for the
  // cart as it was when the page loaded. Only show it while it still matches
  // the cart on screen, so the total never disagrees with the line items.
  const preview =
    serverPreview && !refreshing && Number(serverPreview.subtotal) === Number(cart.subtotal) ? serverPreview : null;
  const awaitingPrice = !!serverPreview && !preview;

  async function handleRemove(itemId: string) {
    await removeFromCart(itemId);
    toast.info('Removed from your cart');
  }

  async function handleClearCart() {
    if (!window.confirm('Remove everything from your cart?')) return;
    await clearCart();
    toast.info('Your cart is now empty');
  }

  const total = preview ? preview.total_amount : awaitingPrice ? null : cart.subtotal;

  return (
    // Scoped to `homeStyles.page` so the reused Home/Listing classes below
    // (crumb, h2, pill, --ink/--line/etc tokens) render correctly, without
    // wrapping -- or restyling -- the page's own header/footer.
    <div className={`${homeStyles.page} ${styles.page}`}>
      <section className={listingStyles.banner}>
        <div className={homeStyles.container}>
          <p className={listingStyles.crumb}>
            <Link href="/">Home</Link>
            <span>/</span>
            <span aria-current="page">Cart</span>
          </p>
          <h1 className={homeStyles.h2}>My Cart</h1>
          <p className={listingStyles.subtitle}>
            {items.length === 0
              ? 'Your cart is empty.'
              : `${items.length} item${items.length === 1 ? '' : 's'} in your cart.`}
          </p>
        </div>
      </section>

      <section className={styles.cartSection}>
        <div className={homeStyles.container}>
          {error && <div className={styles.error}>{error}</div>}

          {items.length === 0 ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>
                <BagIcon size={30} />
              </div>
              <p className={styles.emptyHeading}>Your cart is empty</p>
              <p className={styles.emptyText}>Looks like you haven&apos;t added anything yet.</p>
              <Link href="/products" className={homeStyles.pillOutline}>
                Continue Shopping
              </Link>
            </div>
          ) : (
            <div className={styles.layout}>
              <div className={styles.list}>
                {items.map(item => (
                  <CartRow
                    key={item.id}
                    item={item}
                    disabled={pending}
                    onQtyChange={updateQuantity}
                    onRemove={handleRemove}
                  />
                ))}

                <button type="button" className={styles.clearCartBtn} disabled={pending} onClick={handleClearCart}>
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
                    <path
                      d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2m-9 0 1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                  Clear Cart
                </button>
              </div>

              <div className={styles.summary}>
                <h2 className={styles.summaryTitle}>Order Summary</h2>

                <div className={styles.summaryRow}>
                  <span>Subtotal</span>
                  <span>{formatMoney(cart.subtotal, STOREFRONT_CURRENCY)}</span>
                </div>

                {preview && Number(preview.discount_amount) > 0 && (
                  <div className={styles.summaryRow}>
                    <span>Discount{preview.coupon_code ? ` (${preview.coupon_code})` : ''}</span>
                    <span className={styles.discountValue}>
                      − {formatMoney(preview.discount_amount, STOREFRONT_CURRENCY)}
                    </span>
                  </div>
                )}

                {preview && (
                  <div className={styles.summaryRow}>
                    <span>Shipping</span>
                    <span>
                      {Number(preview.shipping_amount) === 0
                        ? 'Free'
                        : formatMoney(preview.shipping_amount, STOREFRONT_CURRENCY)}
                    </span>
                  </div>
                )}

                {preview && (
                  <div className={styles.summaryRow}>
                    <span>Tax</span>
                    <span>{formatMoney(preview.tax_amount, STOREFRONT_CURRENCY)}</span>
                  </div>
                )}

                <div className={styles.summaryTotalRow}>
                  <span>Total</span>
                  <span>{total === null ? 'Updating…' : formatMoney(total, STOREFRONT_CURRENCY)}</span>
                </div>

                <Link href="/check-out" className={styles.checkoutBtn}>
                  Proceed to Checkout
                </Link>
              </div>
            </div>
          )}
        </div>
      </section>

      <MobileBottomNav />
    </div>
  );
}
