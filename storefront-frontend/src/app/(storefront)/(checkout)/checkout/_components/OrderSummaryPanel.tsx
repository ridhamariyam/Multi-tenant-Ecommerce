'use client';

import Image from 'next/image';
import { useState } from 'react';

import { mediaUrl } from '@/lib/media';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import type { CartItem } from '@/types/cart';
import type { CheckoutPreview, Offer } from '@/types/orders';

import styles from './Checkout.module.css';

function offerDescription(offer: Offer): string {
  const minimum = offer.min_order_amount
    ? ` on orders above ${formatMoney(offer.min_order_amount, offer.currency)}`
    : '';

  switch (offer.discount_type) {
    case 'PERCENTAGE':
      return `${offer.discount_value}% off${minimum}`;
    case 'FIXED_AMOUNT':
      return `${formatMoney(offer.discount_value, offer.currency)} off${minimum}`;
    case 'FREE_SHIPPING':
      return `Free shipping${minimum}`;
    case 'BOGO':
      return `Buy ${offer.buy_quantity ?? 1}, get ${offer.get_quantity ?? 1} with ${offer.discount_value}% off${minimum}`;
  }
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4">
      <path d="M5 12.5 10 17 19 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="M5 5l14 14M19 5 5 19" strokeLinecap="round" />
    </svg>
  );
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      style={{ transform: open ? 'rotate(180deg)' : undefined, transition: 'transform 0.15s ease' }}>
      <path d="m6 9 6 6 6-6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function LockIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" strokeLinecap="round" />
    </svg>
  );
}

function TruckIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M2 6h11v10H2z" strokeLinejoin="round" />
      <path d="M13 10h4l4 3.5V16h-8z" strokeLinejoin="round" />
      <circle cx="6" cy="18" r="1.8" />
      <circle cx="16.5" cy="18" r="1.8" />
    </svg>
  );
}

function ReturnIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 9V4M4 9h5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 9a8 8 0 1 1 2 6.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6l7-3Z" strokeLinejoin="round" />
      <path d="m9 12 2 2 4-4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function SupportIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 13v-1a8 8 0 0 1 16 0v1" strokeLinecap="round" />
      <rect x="2.5" y="13" width="5" height="6" rx="1.5" />
      <rect x="16.5" y="13" width="5" height="6" rx="1.5" />
    </svg>
  );
}

export default function OrderSummaryPanel({
  cartItems,
  preview,
  availableOffers,
  couponInput,
  onCouponInputChange,
  onApplyCoupon,
  onRemoveCoupon,
  couponPending,
  couponError,
  canPlaceOrder,
  placeOrderPending,
  placeOrderError,
  submitLabel,
}: {
  cartItems: CartItem[];
  preview: CheckoutPreview | null;
  availableOffers: Offer[];
  couponInput: string;
  onCouponInputChange: (value: string) => void;
  onApplyCoupon: () => void;
  onRemoveCoupon: () => void;
  couponPending: boolean;
  couponError: string | null;
  canPlaceOrder: boolean;
  placeOrderPending: boolean;
  placeOrderError: string | null;
  /** What the button says: "Place Order", "Pay ₹1,179.99", or what is in progress. */
  submitLabel: string;
}) {
  const [couponOpen, setCouponOpen] = useState(true);
  const [couponsModalOpen, setCouponsModalOpen] = useState(false);

  const appliedCode = preview?.coupon_code ?? null;
  const discount = preview ? Number(preview.discount_amount) : 0;
  const shippingAmount = preview ? Number(preview.shipping_amount) : 0;
  const codFee = preview?.cod_fee ? Number(preview.cod_fee) : 0;

  function selectCoupon(code: string) {
    onCouponInputChange(code);
    setCouponsModalOpen(false);
  }

  return (
    <>
      <div className={styles.summaryCard}>
        <div className={styles.summaryHeader}>
          <p className={styles.summaryTitle}>Order Summary</p>
          <span className={styles.itemCount}>
            {cartItems.length} {cartItems.length === 1 ? 'item' : 'items'}
          </span>
        </div>

        <div className={styles.summaryItems}>
          {cartItems.map(item => (
            <div key={item.id} className={styles.summaryItem}>
              <div className={styles.summaryThumb}>
                {item.image && (
                  <Image src={mediaUrl(item.image.url)} alt={item.image.alt_text ?? item.product_name} fill sizes="52px" />
                )}
              </div>
              <div className={styles.summaryItemBody}>
                <p className={styles.summaryItemName}>{item.product_name}</p>
                <p className={styles.summaryItemMeta}>
                  {item.variant_name} &nbsp;|&nbsp; Qty: {item.quantity}
                </p>
              </div>
              <span className={styles.summaryItemPrice}>{formatMoney(item.subtotal, STOREFRONT_CURRENCY)}</span>
            </div>
          ))}
        </div>

        <div className={styles.couponSection}>
          <div className={styles.couponMobileHeader}>
            <p className={styles.sectionTitle}>Apply Coupon</p>
          </div>

          <button
            type="button"
            className={styles.couponDesktopToggle}
            onClick={() => setCouponOpen(open => !open)}>
            Have a coupon code?
            <ChevronIcon open={couponOpen} />
          </button>

          {couponOpen && !appliedCode && (
            <>
              <div className={styles.couponForm}>
                <input
                  type="text"
                  placeholder="Enter coupon code"
                  className={styles.couponInput}
                  value={couponInput}
                  disabled={couponPending}
                  onChange={event => onCouponInputChange(event.target.value.toUpperCase())}
                />
                <button
                  type="button"
                  className={styles.couponApplyBtn}
                  disabled={couponPending || !couponInput.trim()}
                  onClick={onApplyCoupon}>
                  {couponPending ? 'Checking…' : 'Apply'}
                </button>
              </div>

              <button
                type="button"
                className={styles.viewCouponsLink}
                onClick={() => setCouponsModalOpen(true)}>
                View Available Coupons
              </button>
            </>
          )}

          {couponError && <p className={styles.couponError}>{couponError}</p>}

          {appliedCode && (
            <div className={styles.couponApplied}>
              <span className={styles.couponAppliedIcon}>
                <CheckIcon />
              </span>
              <div className={styles.couponAppliedText}>
                <strong>{appliedCode} applied!</strong>
                <span>You saved {formatMoney(preview?.discount_amount, STOREFRONT_CURRENCY)} on this order.</span>
              </div>
              <button type="button" className={styles.couponRemoveBtn} onClick={onRemoveCoupon} aria-label="Remove coupon">
                <CloseIcon />
              </button>
            </div>
          )}
        </div>

        <div className={styles.summaryTotals}>
          <div className={styles.summaryRow}>
            <span>Subtotal</span>
            <span>{formatMoney(preview?.subtotal, STOREFRONT_CURRENCY)}</span>
          </div>

          {appliedCode && discount > 0 && (
            <div className={styles.summaryRow}>
              <span>Discount ({appliedCode})</span>
              <span className={styles.discountValue}>− {formatMoney(preview?.discount_amount, STOREFRONT_CURRENCY)}</span>
            </div>
          )}

          <div className={styles.summaryRow}>
            <span>Shipping</span>
            <span>{shippingAmount > 0 ? formatMoney(preview?.shipping_amount, STOREFRONT_CURRENCY) : 'Free'}</span>
          </div>

          {codFee > 0 && (
            <div className={styles.summaryRow}>
              <span>Cash on Delivery Fee</span>
              <span>{formatMoney(preview?.cod_fee, STOREFRONT_CURRENCY)}</span>
            </div>
          )}

          <div className={styles.summaryRow}>
            <span>Estimated Tax</span>
            <span>{formatMoney(preview?.tax_amount, STOREFRONT_CURRENCY)}</span>
          </div>
        </div>

        <div className={styles.summaryTotalRow}>
          <span>Total</span>
          <span>{formatMoney(preview?.total_amount, STOREFRONT_CURRENCY)}</span>
        </div>
      </div>

      <div className={styles.trustPanel}>
        <div className={styles.trustItem}>
          <span className={styles.trustIcon}>
            <TruckIcon />
          </span>
          <div>
            <p className={styles.trustTitle}>Free Shipping</p>
            <p className={styles.trustDesc}>On eligible orders</p>
          </div>
        </div>
        <div className={styles.trustItem}>
          <span className={styles.trustIcon}>
            <ReturnIcon />
          </span>
          <div>
            <p className={styles.trustTitle}>Easy Returns</p>
            <p className={styles.trustDesc}>14-day return policy</p>
          </div>
        </div>
        <div className={styles.trustItem}>
          <span className={styles.trustIcon}>
            <ShieldIcon />
          </span>
          <div>
            <p className={styles.trustTitle}>Secure Payment</p>
            <p className={styles.trustDesc}>Your data is protected</p>
          </div>
        </div>
        <div className={styles.trustItem}>
          <span className={styles.trustIcon}>
            <SupportIcon />
          </span>
          <div>
            <p className={styles.trustTitle}>Customer Support</p>
            <p className={styles.trustDesc}>Available 24/7</p>
          </div>
        </div>
      </div>

      <button type="submit" className={styles.placeOrderBtn} disabled={!canPlaceOrder || placeOrderPending}>
        {submitLabel}
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M4 12h16M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>

      {placeOrderError && <p className={styles.couponError}>{placeOrderError}</p>}

      <p className={styles.secureNote}>
        <LockIcon />
        Your payment information is secure and encrypted.
      </p>

      {/* Available Coupons Modal */}
      {couponsModalOpen && (
        <div className={styles.modalOverlay} onClick={() => setCouponsModalOpen(false)}>
          <div className={styles.modalCard} onClick={e => e.stopPropagation()}>
            <div className={styles.modalHeader}>
              <h2 className={styles.modalTitle}>Available Coupons</h2>
              <button
                type="button"
                className={styles.modalCloseBtn}
                onClick={() => setCouponsModalOpen(false)}
                aria-label="Close">
                <CloseIcon />
              </button>
            </div>
            <div className={styles.couponList}>
              {availableOffers.length === 0 ? (
                <p className={styles.couponDescText}>No active coupons are available right now.</p>
              ) : availableOffers.map(coupon => (
                <div key={coupon.code} className={styles.couponCardItem}>
                  <div>
                    <strong className={styles.couponCodeText}>{coupon.code}</strong>
                    <p className={styles.couponDescText}>{offerDescription(coupon)}</p>
                  </div>
                  <button
                    type="button"
                    className={styles.couponSelectBtn}
                    onClick={() => selectCoupon(coupon.code)}>
                    Apply
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
