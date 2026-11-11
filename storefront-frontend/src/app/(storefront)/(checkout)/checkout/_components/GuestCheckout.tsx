'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

import { useBrand } from '@/context/BrandContext';
import { useCart } from '@/context/CartContext';
import { signInUrl } from '@/lib/auth/sign-in-url';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import { confirmGuestPayment, placeGuestOrder, previewGuestCheckout } from '@/lib/orders/guest-actions';
import { pendingOnlinePayment } from '@/lib/payments/online';
import { payWithRazorpay } from '@/lib/payments/razorpay';
import type { CheckoutPreview, Offer, Order, PaymentMethod } from '@/types/orders';
import { toast } from 'react-toastify';

import { PaymentSection } from './Checkout';

import styles from './Checkout.module.css';
import OrderSummaryPanel from './OrderSummaryPanel';
import { taxLabel } from '@/lib/money';

const PINCODE = /^[1-9][0-9]{5}$/;

function newIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

interface Fields {
  name: string;
  phone: string;
  email: string;
  address_line_1: string;
  address_line_2: string;
  city: string;
  state: string;
  postal_code: string;
}

const EMPTY: Fields = {
  name: '',
  phone: '',
  email: '',
  address_line_1: '',
  address_line_2: '',
  city: '',
  state: '',
  postal_code: '',
};

/** Backend field paths ("contact.phone", "address.city") to this form's fields. */
function fieldFor(path: string): keyof Fields | null {
  const leaf = path.split('.').pop() ?? '';
  if (leaf === 'full_name') return 'name';
  return leaf in EMPTY ? (leaf as keyof Fields) : null;
}

/**
 * Checkout without an account: contact, delivery address, and cash on
 * delivery or (when the store has connected Razorpay) UPI / card / net banking. Every amount on screen comes from the backend's guest preview;
 * the order itself is priced again server-side when it is placed.
 */
export default function GuestCheckout({ availableOffers }: { availableOffers: Offer[] }) {
  const router = useRouter();
  const { cart, items: cartItems } = useCart();
  const brand = useBrand();
  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('CASH_ON_DELIVERY');
  const [paid, setPaid] = useState(false);
  const [optIn, setOptIn] = useState(false);

  const [fields, setFields] = useState<Fields>(EMPTY);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof Fields, string>>>({});
  const [preview, setPreview] = useState<CheckoutPreview | null>(null);
  const [pricing, setPricing] = useState(false);
  const [priceError, setPriceError] = useState<string | null>(null);

  const [couponInput, setCouponInput] = useState('');
  const [couponCode, setCouponCode] = useState<string | null>(null);
  const [couponPending, setCouponPending] = useState(false);
  const [couponError, setCouponError] = useState<string | null>(null);

  const [placing, setPlacing] = useState(false);
  const [placeError, setPlaceError] = useState<string | null>(null);
  const [placed, setPlaced] = useState<Order | null>(null);
  const [idempotencyKey] = useState(newIdempotencyKey);

  const pincode = PINCODE.test(fields.postal_code) ? fields.postal_code : null;
  const latest = useRef(0);

  // Re-price whenever the bag, the delivery pincode or the coupon changes.
  useEffect(() => {
    if (placed || cartItems.length === 0) return;
    const run = ++latest.current;
    setPricing(true);
    previewGuestCheckout({ pincode, couponCode, paymentMethod }).then(result => {
      if (run !== latest.current) return;
      setPricing(false);
      if (result.preview) {
        setPreview(result.preview);
        setPriceError(null);
      } else if (couponCode) {
        // The coupon stopped applying to this bag: drop it and price without it.
        setCouponError(result.error);
        setCouponCode(null);
      } else {
        setPreview(null);
        setPriceError(result.error);
      }
    });
  }, [cart, pincode, couponCode, paymentMethod, placed, cartItems.length]);

  function update(name: keyof Fields, value: string) {
    setFields(current => ({ ...current, [name]: value }));
    setFieldErrors(current => ({ ...current, [name]: undefined }));
  }

  async function applyCoupon() {
    const code = couponInput.trim().toUpperCase();
    if (!code) return;
    setCouponPending(true);
    setCouponError(null);
    const result = await previewGuestCheckout({ pincode, couponCode: code, paymentMethod });
    setCouponPending(false);
    if (result.error || !result.preview) {
      setCouponError(result.error ?? 'That coupon could not be applied.');
      return;
    }
    setCouponCode(code);
    setPreview(result.preview);
    setCouponInput('');
  }

  function removeCoupon() {
    setCouponCode(null);
    setCouponError(null);
  }

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (placing) return;

    setPlacing(true);
    setPlaceError(null);
    const result = await placeGuestOrder({
      contact: {
        name: fields.name.trim(),
        phone: fields.phone.trim(),
        email: fields.email.trim() || null,
        marketing_opt_in: optIn && !!fields.email.trim(),
      },
      address: {
        full_name: fields.name.trim(),
        phone: fields.phone.trim(),
        address_line_1: fields.address_line_1.trim(),
        address_line_2: fields.address_line_2.trim() || null,
        city: fields.city.trim(),
        state: fields.state.trim(),
        postal_code: fields.postal_code.trim(),
        country: 'India',
      },
      couponCode,
      idempotencyKey,
      paymentMethod,
    });
    setPlacing(false);

    if (result.status === 'placed') {
      setPlaced(result.order);
      window.scrollTo({ top: 0 });
      // The bag is now empty; let the header badge and drawer catch up.
      router.refresh();
      const payment = pendingOnlinePayment(result.order);
      if (payment) setPaid(await payGuestOrder(payment, brand));
      return;
    }

    const mapped: Partial<Record<keyof Fields, string>> = {};
    for (const [path, text] of Object.entries(result.fieldErrors)) {
      const field = fieldFor(path);
      if (field && !mapped[field]) mapped[field] = text;
    }
    setFieldErrors(mapped);
    setPlaceError(Object.keys(mapped).length ? 'Please check the highlighted fields.' : result.message);
  }

  if (placed) return <GuestOrderPlaced order={placed} paid={paid} onPaid={() => setPaid(true)} />;

  const codUnavailable = preview?.cod && !preview.cod.available ? (preview.cod.message ?? 'Cash on delivery is not available for this order.') : null;
  const codFee = preview?.cod_fee && Number(preview.cod_fee) > 0 ? formatMoney(preview.cod_fee, STOREFRONT_CURRENCY) : null;
  const methodBlocked = paymentMethod === 'CASH_ON_DELIVERY' ? !!codUnavailable : !brand.onlinePayments;
  const canPlace = cartItems.length > 0 && !pricing && !methodBlocked && !priceError;

  const input = (name: keyof Fields, label: string, props: React.InputHTMLAttributes<HTMLInputElement> = {}, full = false) => (
    <div className={`${styles.formField} ${full ? styles.formFieldFull : ''}`}>
      <label className={styles.formLabel} htmlFor={`guest-${name}`}>
        {label}
      </label>
      <input
        id={`guest-${name}`}
        name={name}
        className={styles.formInput}
        value={fields[name]}
        onChange={event => update(name, event.target.value)}
        disabled={placing}
        aria-invalid={!!fieldErrors[name]}
        aria-describedby={fieldErrors[name] ? `guest-${name}-error` : undefined}
        {...props}
      />
      {fieldErrors[name] && (
        <span id={`guest-${name}-error`} className={styles.couponError} role="alert">
          {fieldErrors[name]}
        </span>
      )}
    </div>
  );

  return (
    <div className={styles.page}>
      <form onSubmit={submit} className={styles.container} noValidate={false}>
        <nav className={styles.breadcrumb} aria-label="Checkout progress">
          <Link href="/cart">Cart</Link>
          <span>›</span>
          <span className={styles.breadcrumbCurrent}>Checkout</span>
          <span>›</span>
          <span>Order Confirmed</span>
        </nav>

        <h1 className={styles.heading}>Checkout</h1>
        <p className={styles.subtitle}>
          Checking out as a guest.{' '}
          <Link href={signInUrl('/checkout')}>Sign in</Link> to use your saved addresses.
        </p>

        {cartItems.length === 0 && <div className={styles.error}>Your bag is empty -- add something before checking out.</div>}
        {priceError && cartItems.length > 0 && <div className={styles.error}>{priceError}</div>}

        <div className={styles.grid}>
          <div className={styles.main}>
            <section>
              <div className={styles.sectionHeader}>
                <div className={styles.sectionTitleGroup}>
                  <h2 className={styles.sectionTitle}>Contact</h2>
                </div>
              </div>
              <div className={`${styles.card} ${styles.formGrid} ${styles.guestCard}`}>
                {input('name', 'Full name', { required: true, autoComplete: 'name', maxLength: 150 }, true)}
                {input('phone', 'Mobile number', {
                  required: true,
                  type: 'tel',
                  inputMode: 'tel',
                  autoComplete: 'tel',
                  placeholder: '10-digit mobile number',
                  maxLength: 16,
                })}
                {input('email', 'Email (optional)', { type: 'email', autoComplete: 'email', maxLength: 255 })}
                <label className={`${styles.formField} ${styles.formFieldFull} ${styles.optIn}`}>
                  <input
                    type="checkbox"
                    checked={optIn}
                    disabled={placing || !fields.email.trim()}
                    onChange={event => setOptIn(event.target.checked)}
                  />{' '}
                  Email me new arrivals and offers (unsubscribe any time)
                </label>
              </div>
            </section>

            <section>
              <div className={styles.sectionHeader}>
                <div className={styles.sectionTitleGroup}>
                  <h2 className={styles.sectionTitle}>Delivery Address</h2>
                </div>
              </div>
              <div className={`${styles.card} ${styles.formGrid} ${styles.guestCard}`}>
                {input('address_line_1', 'Address', { required: true, autoComplete: 'address-line1', maxLength: 255 }, true)}
                {input('address_line_2', 'Apartment, landmark (optional)', { autoComplete: 'address-line2', maxLength: 255 }, true)}
                {input('city', 'City', { required: true, autoComplete: 'address-level2', maxLength: 100 })}
                {input('state', 'State', { required: true, autoComplete: 'address-level1', maxLength: 100 })}
                {input('postal_code', 'Pincode', {
                  required: true,
                  inputMode: 'numeric',
                  autoComplete: 'postal-code',
                  pattern: '[1-9][0-9]{5}',
                  maxLength: 6,
                  title: 'A 6-digit pincode',
                })}
                <div className={styles.formField}>
                  <span className={styles.formLabel}>Country</span>
                  <input className={styles.formInput} value="India" disabled readOnly aria-label="Country" />
                </div>
              </div>
            </section>

            <PaymentSection
              selected={paymentMethod}
              onSelect={setPaymentMethod}
              disabled={placing}
              codUnavailableReason={codUnavailable}
              codFee={codFee}
              onlineUnavailableReason={brand.onlinePayments ? null : 'Not offered by this store yet'}
            />
          </div>

          <div className={styles.sidebar}>
            <OrderSummaryPanel
              cartItems={cartItems}
              preview={preview}
              availableOffers={availableOffers}
              couponInput={couponInput}
              onCouponInputChange={setCouponInput}
              onApplyCoupon={applyCoupon}
              onRemoveCoupon={removeCoupon}
              couponPending={couponPending}
              couponError={couponError}
              canPlaceOrder={canPlace}
              placeOrderPending={placing}
              submitLabel={
                placing ? 'Placing order…' : pricing ? 'Updating price…' : paymentMethod === 'CASH_ON_DELIVERY' ? 'Place Order' : 'Place Order & Pay'
              }
              placeOrderError={placeError}
            />
          </div>
        </div>
      </form>
    </div>
  );
}

/** Open Razorpay for a guest order and confirm the payment; true once confirmed. */
async function payGuestOrder(
  payment: NonNullable<ReturnType<typeof pendingOnlinePayment>>,
  brand: { razorpayKeyId: string | null; name: string },
): Promise<boolean> {
  try {
    const outcome = await payWithRazorpay(payment, {
      onAttemptFailed: text => toast.error(text),
      keyId: brand.razorpayKeyId,
      storeName: brand.name,
    });
    if (outcome.kind === 'dismissed') {
      toast.info('Payment not completed. Your order is saved -- you can pay below.');
      return false;
    }
    const result = await confirmGuestPayment(outcome.verification);
    if (!result.ok) {
      toast.error(result.message ?? 'We could not confirm your payment yet. If money left your account, it will be confirmed shortly.');
      return false;
    }
    toast.success('Payment received. Thank you!');
    return true;
  } catch (error) {
    toast.error(error instanceof Error ? error.message : 'Could not open the payment window.');
    return false;
  }
}

/** Shown in place of the form once the order is in. */
function GuestOrderPlaced({ order, paid, onPaid }: { order: Order; paid: boolean; onPaid: () => void }) {
  const brand = useBrand();
  const [paying, setPaying] = useState(false);
  const money = (amount: string | null | undefined) => formatMoney(amount, order.currency || STOREFRONT_CURRENCY);
  const payment = pendingOnlinePayment(order);
  const online = order.payment_method !== 'CASH_ON_DELIVERY';
  const trackHref = `/track-order?order=${encodeURIComponent(order.order_number)}`;

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.heading}>Thank you -- your order is placed</h1>
        <p className={styles.subtitle}>
          Order <strong>{order.order_number}</strong>. Keep this number: with your phone number it lets you track the
          order any time.
        </p>

        <div className={styles.grid}>
          <div className={styles.main}>
            <section className={styles.card}>
              <h2 className={styles.sectionTitle}>Items</h2>
              {order.items.map(item => (
                <div key={item.variant_id} className={styles.summaryRow}>
                  <span>
                    {item.product_name}
                    {item.variant_name ? ` · ${item.variant_name}` : ''} × {item.quantity}
                  </span>
                  <span>{money(item.subtotal)}</span>
                </div>
              ))}
            </section>

            <section className={styles.card}>
              <h2 className={styles.sectionTitle}>Delivering to</h2>
              <p>
                {order.delivery_address.full_name}, {order.delivery_address.phone}
                <br />
                {order.delivery_address.address_line_1}
                {order.delivery_address.address_line_2 ? `, ${order.delivery_address.address_line_2}` : ''}
                <br />
                {order.delivery_address.city}, {order.delivery_address.state} {order.delivery_address.postal_code}
              </p>
            </section>
          </div>

          <div className={styles.sidebar}>
            <section className={styles.summaryCard}>
              <p className={styles.summaryTitle}>Order Summary</p>
              <div className={styles.summaryRow}>
                <span>Subtotal</span>
                <span>{money(order.subtotal)}</span>
              </div>
              {Number(order.discount_amount) > 0 && (
                <div className={styles.summaryRow}>
                  <span>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</span>
                  <span>− {money(order.discount_amount)}</span>
                </div>
              )}
              <div className={styles.summaryRow}>
                <span>Shipping</span>
                <span>{Number(order.shipping_amount) === 0 ? 'Free' : money(order.shipping_amount)}</span>
              </div>
              {Number(order.cod_fee) > 0 && (
                <div className={styles.summaryRow}>
                  <span>COD fee</span>
                  <span>{money(order.cod_fee)}</span>
                </div>
              )}
              <div className={styles.summaryRow}>
                <span>{taxLabel(order)}</span>
                <span>{money(order.tax_amount)}</span>
              </div>
              <div className={styles.summaryRow}>
                <strong>{!online ? 'Pay on delivery' : paid ? 'Paid' : 'To pay'}</strong>
                <strong>{money(order.total_amount)}</strong>
              </div>
              {online && !paid && payment && (
                <button
                  type="button"
                  className={styles.placeOrderBtn}
                  disabled={paying}
                  onClick={async () => {
                    setPaying(true);
                    if (await payGuestOrder(payment, brand)) onPaid();
                    setPaying(false);
                  }}>
                  {paying ? 'Processing payment…' : `Pay ${money(order.total_amount)}`}
                </button>
              )}
              <Link href={trackHref} className={styles.placeOrderBtn}>
                Track this order
              </Link>
              <p className={styles.secureNote}>
                Sign in later with {order.delivery_address.phone} to see this order in your account.
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
