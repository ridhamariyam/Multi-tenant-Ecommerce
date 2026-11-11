'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useActionState, useEffect, useRef, useState, useTransition } from 'react';
import { toast } from 'react-toastify';

import { useCart } from '@/context/CartContext';
import { confirmOnlinePayment, deleteAddress, placeOrder, previewCheckoutFor } from '@/lib/orders/actions';
import { initialCheckoutState } from '@/lib/orders/state';
import { payWithRazorpay } from '@/lib/payments/razorpay';
import { STOREFRONT_CURRENCY } from '@/lib/currency';
import { formatMoney } from '@/lib/format';
import type { Address } from '@/types/addresses';
import { PAYMENT_METHOD_LABELS, type CheckoutPreview, type Offer, type PaymentMethod } from '@/types/orders';

import AddressFormModal from './AddressFormModal';
import DeleteConfirmModal from './DeleteConfirmModal';
import styles from './Checkout.module.css';
import OrderSummaryPanel from './OrderSummaryPanel';

function generateIdempotencyKey(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

// -----------------------------------
// ICONS
// -----------------------------------

function ChevronRightIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8">
      <path d="m9 6 6 6-6 6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function TrashIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path
        d="M4 7h16M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2m-9 0 1 13a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-13"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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

function CardIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2.5" y="5.5" width="19" height="13" rx="2" />
      <path d="M2.5 10h19" strokeLinecap="round" />
    </svg>
  );
}

function CodIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="2.5" y="7" width="19" height="12" rx="2" />
      <circle cx="12" cy="13" r="3" />
      <path d="M2.5 10.5h3M18.5 10.5h3" strokeLinecap="round" />
    </svg>
  );
}

function BankIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M3 9.5 12 4l9 5.5" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 10v7M9.5 10v7M14.5 10v7M19 10v7M3 20h18" strokeLinecap="round" />
    </svg>
  );
}

function PayPalIcon() {
  return (
    <span style={{ background: '#003087' }} className={styles.methodBadge}>
      P
    </span>
  );
}

function UpiIcon() {
  return (
    <span style={{ background: '#1a1a1a', fontSize: '9px' }} className={styles.methodBadge}>
      UPI
    </span>
  );
}

// -----------------------------------
// ADDRESS SECTION
// -----------------------------------

function AddressSection({
  addresses,
  selectedId,
  disabled,
  onSelect,
  onEdit,
  onDeleteRequest,
  onAddNew,
}: {
  addresses: Address[];
  selectedId: string | null;
  disabled: boolean;
  onSelect: (id: string) => void;
  onEdit: (address: Address) => void;
  onDeleteRequest: (address: Address) => void;
  onAddNew: () => void;
}) {
  return (
    <section>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleGroup}>
          <h2 className={styles.sectionTitle}>Delivery Address</h2>
        </div>
        <Link href="/my-account" className={styles.manageLink}>
          Manage Addresses
        </Link>
      </div>

      <div className={styles.card}>
        {addresses.length === 0 ? (
          <p className={styles.emptyAddresses}>No saved addresses yet -- add one below.</p>
        ) : (
          addresses.map(address => {
            const selected = address.id === selectedId;
            return (
              <div key={address.id} className={`${styles.row} ${selected ? styles.rowSelected : ''}`}>
                <input
                  type="radio"
                  name="delivery_address"
                  className={styles.radio}
                  checked={selected}
                  disabled={disabled}
                  onChange={() => onSelect(address.id)}
                  aria-label={`Deliver to ${address.full_name}`}
                />
                <div className={styles.addressBody} onClick={() => !disabled && onSelect(address.id)}>
                  <div className={styles.addressTopLine}>
                    <span className={styles.addressLabel}>{address.full_name}</span>
                    {address.is_default && <span className={styles.defaultBadge}>Default</span>}
                  </div>
                  <p className={styles.addressLine}>
                    {address.address_line_1}
                    {address.address_line_2 ? `, ${address.address_line_2}` : ''}
                  </p>
                  <p className={styles.addressLine}>
                    {address.city}, {address.state} {address.postal_code}, {address.country}
                  </p>
                  <p className={styles.addressLine}>{address.phone}</p>
                </div>
                <div className={styles.addressActions}>
                  <button
                    type="button"
                    className={styles.addressEdit}
                    onClick={() => onEdit(address)}
                    disabled={disabled}>
                    Edit
                    <ChevronRightIcon />
                  </button>
                  <button
                    type="button"
                    className={styles.addressDelete}
                    onClick={() => onDeleteRequest(address)}
                    disabled={disabled}
                    aria-label={`Delete address: ${address.full_name}`}>
                    <TrashIcon />
                  </button>
                </div>
              </div>
            );
          })
        )}
      </div>

      <button type="button" className={styles.addAddressBtn} onClick={onAddNew} disabled={disabled}>
        <span style={{ fontSize: '16px', lineHeight: 1 }}>+</span> Add New Address
      </button>
    </section>
  );
}

// -----------------------------------
// SHIPPING SECTION
// -----------------------------------

function ShippingSection({ preview }: { preview: CheckoutPreview | null }) {
  const shippingAmount = preview ? Number(preview.shipping_amount) : 0;

  return (
    <section>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleGroup}>
          <h2 className={styles.sectionTitle}>Shipping Method</h2>
        </div>
      </div>

      <div className={styles.card}>
        <div className={styles.row}>
          <input type="radio" name="shipping_method" className={styles.radio} checked readOnly aria-label="Standard shipping" />
          <span className={styles.methodIcon}>
            <TruckIcon />
          </span>
          <div className={styles.methodBody}>
            <p className={styles.methodTitle}>Standard Shipping</p>
            <p className={styles.methodDesc}>5 - 7 business days</p>
          </div>
          <span className={styles.methodPrice}>
            {shippingAmount > 0 ? formatMoney(preview?.shipping_amount, STOREFRONT_CURRENCY) : 'Free'}
          </span>
        </div>

        <div className={`${styles.row} ${styles.rowDisabled}`}>
          <input type="radio" name="shipping_method" className={styles.radio} disabled aria-label="Express shipping" />
          <span className={styles.methodIcon}>
            <TruckIcon />
          </span>
          <div className={styles.methodBody}>
            <p className={styles.methodTitle}>
              Express Shipping <span className={styles.comingSoon}>Coming soon</span>
            </p>
            <p className={styles.methodDesc}>2 - 3 business days</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// -----------------------------------
// PAYMENT SECTION
// -----------------------------------

const PAYMENT_OPTIONS: { method: PaymentMethod; description: string }[] = [
  { method: 'UPI', description: 'Google Pay, PhonePe, Paytm or any UPI app' },
  { method: 'CREDIT_CARD', description: 'Visa, Mastercard, RuPay, AMEX, etc.' },
  { method: 'DEBIT_CARD', description: 'Visa, Mastercard, RuPay, Maestro, etc.' },
  { method: 'NET_BANKING', description: 'All major Indian banks' },
  { method: 'CASH_ON_DELIVERY', description: 'Pay when your order is delivered' },
];

function PaymentMethodIcon({ method }: { method: PaymentMethod }) {
  if (method === 'UPI') return <UpiIcon />;

  return (
    <span className={styles.methodIcon}>
      {method === 'NET_BANKING' ? <BankIcon /> : method === 'CASH_ON_DELIVERY' ? <CodIcon /> : <CardIcon />}
    </span>
  );
}

function PaymentSection({
  selected,
  onSelect,
  disabled,
  codUnavailableReason,
  codFee,
}: {
  selected: PaymentMethod;
  onSelect: (method: PaymentMethod) => void;
  disabled: boolean;
  /** Set when the backend says this order cannot be paid in cash. */
  codUnavailableReason: string | null;
  codFee: string | null;
}) {
  return (
    <section>
      <div className={styles.sectionHeader}>
        <div className={styles.sectionTitleGroup}>
          <h2 className={styles.sectionTitle}>Payment Method</h2>
        </div>
      </div>

      <div className={styles.card}>
        {PAYMENT_OPTIONS.map(({ method, description }) => {
          const isCod = method === 'CASH_ON_DELIVERY';
          const unavailable = isCod && codUnavailableReason !== null;
          const isSelected = selected === method;

          return (
            <label
              key={method}
              className={`${styles.row} ${isSelected ? styles.rowSelected : ''} ${unavailable ? styles.rowDisabled : ''}`}>
              <input
                type="radio"
                name="payment_method_choice"
                className={styles.radio}
                checked={isSelected}
                disabled={disabled || unavailable}
                onChange={() => onSelect(method)}
              />
              <PaymentMethodIcon method={method} />
              <div className={styles.methodBody}>
                <p className={styles.methodTitle}>{PAYMENT_METHOD_LABELS[method]}</p>
                <p className={styles.methodDesc}>
                  {unavailable ? codUnavailableReason : isCod && codFee ? `${description} (+${codFee} fee)` : description}
                </p>
              </div>
              {(method === 'CREDIT_CARD' || method === 'DEBIT_CARD') && (
                <div className={styles.cardNetworks}>
                  <span>VISA</span>
                  <span>MC</span>
                  <span>RUPAY</span>
                </div>
              )}
            </label>
          );
        })}

        <div className={`${styles.row} ${styles.rowDisabled}`}>
          <input type="radio" name="payment_method_choice" className={styles.radio} disabled aria-label="PayPal" />
          <PayPalIcon />
          <div className={styles.methodBody}>
            <p className={styles.methodTitle}>
              PayPal <span className={styles.comingSoon}>Coming soon</span>
            </p>
            <p className={styles.methodDesc}>Pay with PayPal</p>
          </div>
        </div>
      </div>

      {selected !== 'CASH_ON_DELIVERY' && (
        <p className={styles.methodDesc} style={{ marginTop: 10 }}>
          You&apos;ll pay securely through Razorpay after placing the order.
        </p>
      )}

      <label className={styles.billingRow}>
        <input type="checkbox" defaultChecked disabled />
        Billing address is the same as delivery address
      </label>
    </section>
  );
}

// -----------------------------------
// CHECKOUT
// -----------------------------------

export default function Checkout({
  initialAddresses,
  initialPreview,
  availableOffers,
}: {
  initialAddresses: Address[];
  initialPreview: CheckoutPreview | null;
  availableOffers: Offer[];
}) {
  const router = useRouter();
  const { cart, items: cartItems } = useCart();

  const [addresses, setAddresses] = useState(initialAddresses);
  useEffect(() => setAddresses(initialAddresses), [initialAddresses]);

  const [preview, setPreview] = useState(initialPreview);
  useEffect(() => setPreview(initialPreview), [initialPreview]);

  const [selectedAddressId, setSelectedAddressId] = useState<string | null>(
    () => addresses.find(address => address.is_default)?.id ?? addresses[0]?.id ?? null,
  );
  useEffect(() => {
    if (selectedAddressId && addresses.some(address => address.id === selectedAddressId)) return;
    setSelectedAddressId(addresses.find(address => address.is_default)?.id ?? addresses[0]?.id ?? null);
  }, [addresses, selectedAddressId]);

  const [modalOpen, setModalOpen] = useState(false);
  const [editingAddress, setEditingAddress] = useState<Address | null>(null);

  // Address Deletion state
  const [addressToDelete, setAddressToDelete] = useState<Address | null>(null);

  const [couponInput, setCouponInput] = useState('');
  const [couponPending, setCouponPending] = useState(false);
  const [couponError, setCouponError] = useState<string | null>(null);

  const [idempotencyKey] = useState(generateIdempotencyKey);
  const [placeState, placeFormAction, placePending] = useActionState(placeOrder, initialCheckoutState);

  const [paymentMethod, setPaymentMethod] = useState<PaymentMethod>('UPI');
  const [paying, setPaying] = useState(false);
  const [confirming, startConfirm] = useTransition();
  const openedForRef = useRef<string | null>(null);

  const codUnavailableReason =
    preview?.cod && !preview.cod.available ? (preview.cod.message ?? 'Not available for this order') : null;
  const codFee = preview?.cod_fee && Number(preview.cod_fee) > 0 ? formatMoney(preview.cod_fee, STOREFRONT_CURRENCY) : null;

  // Cash can stop being allowed once an address or coupon changes the order.
  useEffect(() => {
    if (codUnavailableReason && paymentMethod === 'CASH_ON_DELIVERY') setPaymentMethod('UPI');
  }, [codUnavailableReason, paymentMethod]);

  // The total can depend on the method (a cash-on-delivery fee), so re-price
  // whenever the preview on screen was priced for a different one.
  useEffect(() => {
    if (!preview?.payment_method || preview.payment_method === paymentMethod) return;

    let stale = false;
    previewCheckoutFor(selectedAddressId, preview.coupon_code, paymentMethod).then(result => {
      if (!stale && result.preview) setPreview(result.preview);
    });
    return () => {
      stale = true;
    };
  }, [paymentMethod, preview?.payment_method, preview?.coupon_code, selectedAddressId]);

  // Re-price whenever the cart changes on this page (e.g. a quantity change in
  // the cart drawer), keeping the chosen address, coupon and payment method.
  // If the coupon no longer applies to the new cart, drop it and say so.
  const pricedCartRef = useRef(cart);
  useEffect(() => {
    if (pricedCartRef.current === cart) return;
    pricedCartRef.current = cart;

    let stale = false;
    const coupon = preview?.coupon_code ?? null;
    (async () => {
      let result = await previewCheckoutFor(selectedAddressId, coupon, paymentMethod);
      if (result.error && coupon) {
        result = await previewCheckoutFor(selectedAddressId, null, paymentMethod);
        if (!stale && result.preview) toast.info(`Coupon ${coupon} no longer applies to your cart.`);
      }
      if (!stale && result.preview) setPreview(result.preview);
    })();
    return () => {
      stale = true;
    };
    // Only a cart change should trigger this; the other inputs have their own handlers.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cart]);

  // The order is placed and waits on Razorpay: open Checkout once for it.
  useEffect(() => {
    if (placeState.status !== 'pay' || !placeState.payment) return;
    const request = placeState.payment;
    if (openedForRef.current === request.razorpayOrderId) return;
    openedForRef.current = request.razorpayOrderId;

    const orderPage = `/order-confirmation/${encodeURIComponent(request.orderNumber)}`;
    setPaying(true);

    payWithRazorpay(request, { onAttemptFailed: message => toast.error(message) })
      .then(outcome => {
        if (outcome.kind === 'dismissed') {
          toast.info('Payment not completed. Your order is saved -- you can pay for it from the order page.');
          router.push(orderPage);
          return;
        }

        startConfirm(async () => {
          const result = await confirmOnlinePayment(request.orderNumber, outcome.verification);
          if (result.status === 'error') {
            toast.error(result.message ?? 'We could not confirm your payment yet.');
            router.push(orderPage);
          }
        });
      })
      .catch((error: unknown) => {
        toast.error(error instanceof Error ? error.message : 'Could not open the payment window.');
        router.push(orderPage);
      })
      .finally(() => setPaying(false));
  }, [placeState, router]);

  async function handleApplyCoupon() {
    const code = couponInput.trim();
    if (!code) return;

    setCouponPending(true);
    setCouponError(null);
    const result = await previewCheckoutFor(selectedAddressId, code, paymentMethod);
    setCouponPending(false);

    if (result.error) {
      setCouponError(result.error);
      return;
    }

    setPreview(result.preview);
    setCouponInput('');
  }

  async function handleRemoveCoupon() {
    setCouponPending(true);
    const result = await previewCheckoutFor(selectedAddressId, null, paymentMethod);
    setCouponPending(false);
    setCouponError(null);
    setPreview(result.preview);
  }

  function openAddModal() {
    setEditingAddress(null);
    setModalOpen(true);
  }

  function openEditModal(address: Address) {
    setEditingAddress(address);
    setModalOpen(true);
  }

  function handleAddressSaved() {
    setModalOpen(false);
    router.refresh();
  }

  function handleConfirmDeleteAddress(address: Address) {
    setAddressToDelete(address);
  }

  async function executeDeleteAddress() {
    if (!addressToDelete) return;
    const targetAddress = addressToDelete;
    setAddressToDelete(null);

    const formData = new FormData();
    formData.set('address_id', targetAddress.id);

    const result = await deleteAddress(initialCheckoutState, formData);

    if (result.status === 'error') {
      toast.error(result.message ?? 'Could not delete that address.');
      return;
    }

    toast.info('Address removed');
    if (selectedAddressId === targetAddress.id) setSelectedAddressId(null);
    router.refresh();
  }

  const canPlaceOrder = Boolean(selectedAddressId) && cartItems.length > 0;
  const busy = placePending || paying || confirming || placeState.status === 'pay';
  const isOnline = paymentMethod !== 'CASH_ON_DELIVERY';

  let submitLabel = isOnline ? `Pay ${formatMoney(preview?.total_amount, STOREFRONT_CURRENCY)}` : 'Place Order';
  if (placePending) submitLabel = 'Placing order…';
  else if (confirming) submitLabel = 'Confirming payment…';
  else if (paying || placeState.status === 'pay') submitLabel = 'Waiting for payment…';

  return (
    <div className={styles.page}>
      <form action={placeFormAction} className={styles.container}>
        <input type="hidden" name="address_id" value={selectedAddressId ?? ''} />
        <input type="hidden" name="coupon_code" value={preview?.coupon_code ?? ''} />
        <input type="hidden" name="idempotency_key" value={idempotencyKey} />
        <input type="hidden" name="payment_method" value={paymentMethod} />

        <nav className={styles.breadcrumb} aria-label="Checkout progress">
          <Link href="/cart-items">Cart</Link>
          <span>›</span>
          <span className={styles.breadcrumbCurrent}>Checkout</span>
          <span>›</span>
          <span>Payment</span>
          <span>›</span>
          <span>Order Confirmed</span>
        </nav>

        <h1 className={styles.heading}>Checkout</h1>
        <p className={styles.subtitle}>Complete your order securely and easily.</p>

        {cartItems.length === 0 && !busy && <div className={styles.error}>Your cart is empty -- add something before checking out.</div>}

        <div className={styles.grid}>
          <div className={styles.main}>
            <AddressSection
              addresses={addresses}
              selectedId={selectedAddressId}
              disabled={busy}
              onSelect={setSelectedAddressId}
              onEdit={openEditModal}
              onDeleteRequest={handleConfirmDeleteAddress}
              onAddNew={openAddModal}
            />
            <ShippingSection preview={preview} />
            <PaymentSection
              selected={paymentMethod}
              onSelect={setPaymentMethod}
              disabled={busy}
              codUnavailableReason={codUnavailableReason}
              codFee={codFee}
            />
          </div>

          <div className={styles.sidebar}>
            <OrderSummaryPanel
              cartItems={cartItems}
              preview={preview}
              availableOffers={availableOffers}
              couponInput={couponInput}
              onCouponInputChange={setCouponInput}
              onApplyCoupon={handleApplyCoupon}
              onRemoveCoupon={handleRemoveCoupon}
              couponPending={couponPending}
              couponError={couponError}
              canPlaceOrder={canPlaceOrder}
              placeOrderPending={busy}
              submitLabel={submitLabel}
              placeOrderError={placeState.status === 'error' ? placeState.message : null}
            />
          </div>
        </div>
      </form>

      {modalOpen && (
        <AddressFormModal address={editingAddress} onClose={() => setModalOpen(false)} onSaved={handleAddressSaved} />
      )}

      {addressToDelete && (
        <DeleteConfirmModal
          message={`Are you sure you want to delete the address "${addressToDelete.full_name}"?`}
          onConfirm={executeDeleteAddress}
          onCancel={() => setAddressToDelete(null)}
        />
      )}
    </div>
  );
}
