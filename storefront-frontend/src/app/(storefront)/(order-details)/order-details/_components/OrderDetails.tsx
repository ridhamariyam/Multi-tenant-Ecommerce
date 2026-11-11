'use client';

import Image from 'next/image';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, useTransition } from 'react';
import { toast } from 'react-toastify';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { useCart } from '@/context/CartContext';
import { formatDate, formatDateTime, formatMoney } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import { cancelOrder } from '@/lib/orders/actions';
import { initialCheckoutState } from '@/lib/orders/state';
import { ORDER_STEPS, orderStatusMeta, orderStepIndex, paymentStatusMeta, type StatusTone } from '@/lib/orders/status';
import { paymentMethodLabel } from '@/lib/payments/online';
import type { CourierTracking, Order, OrderStatus, Payment, TrackingEvent } from '@/types/orders';

import styles from './OrderDetails.module.css';

/** What the catalogue still says about each ordered product, keyed by product id. */
export type OrderItemProducts = Record<
  string,
  | {
      image: { url: string; alt_text: string | null } | null;
      slug: string | null;
      /** Variants that can be added to the cart right now. */
      inStockVariantIds: string[];
    }
  | undefined
>;

const TONE: Record<StatusTone, string> = {
  amber: styles.toneAmber,
  blue: styles.toneBlue,
  green: styles.toneGreen,
  red: styles.toneRed,
  neutral: styles.toneNeutral,
};

const PROVIDER_LABELS: Record<Payment['provider'], string> = {
  COD: 'Cash on delivery',
  PREPAID: 'Advance',
  RAZORPAY: 'Online',
};

/** Statuses that end the order off the forward line, shown as a final step. */
const TERMINAL: readonly OrderStatus[] = ['CANCELLED', 'RETURN_REQUESTED', 'RETURNED', 'REFUNDED'];

/** Statuses after which an estimated delivery date no longer means anything. */
const NO_ESTIMATE: readonly OrderStatus[] = ['DELIVERED', ...TERMINAL];

interface TimelineStep {
  label: string;
  state: 'done' | 'current' | 'upcoming' | 'stopped';
  date: string | null;
  note: string | null;
}

/**
 * The order's lifecycle, as far as it really got.
 *
 * Steps are completed from the current status; dates come only from
 * `created_at` (Order Placed) and the recorded tracking events, so a step
 * the backend has no event for shows no date rather than a made-up one.
 * Cancellation and returns stop the line where the history says it stopped.
 */
function buildTimeline(order: Order, events: TrackingEvent[]): TimelineStep[] {
  const firstAt = (statuses: readonly OrderStatus[]) =>
    events.find(event => event.status && statuses.includes(event.status))?.occurred_at ?? null;
  const stepDate = (index: number) => (index === 0 ? order.created_at : firstAt(ORDER_STEPS[index].statuses));

  if (TERMINAL.includes(order.status)) {
    const reached = Math.max(
      0,
      ...events.map(event => (event.status ? orderStepIndex(event.status) : -1)),
    );
    return [
      ...ORDER_STEPS.slice(0, reached + 1).map((step, index) => ({
        label: step.label,
        state: 'done' as const,
        date: stepDate(index),
        note: null,
      })),
      {
        label: orderStatusMeta(order.status).label,
        state: 'stopped',
        date: firstAt([order.status]),
        note: null,
      },
    ];
  }

  const current = orderStepIndex(order.status);
  return ORDER_STEPS.map((step, index) => {
    const isCurrent = index === current;
    return {
      label: step.label,
      state: index < current ? 'done' : isCurrent ? 'current' : 'upcoming',
      date: index <= current ? stepDate(index) : null,
      // PACKED and OUT_FOR_DELIVERY share a step with their neighbour; name them.
      note: isCurrent && step.statuses[0] !== order.status ? orderStatusMeta(order.status).label : null,
    };
  });
}

/** Only http(s) tracking links are followed; anything else is not a URL to send a shopper to. */
function safeUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'https:' || parsed.protocol === 'http:' ? parsed.toString() : null;
  } catch {
    return null;
  }
}

const amount = (value: string | null | undefined) => Number(value ?? 0) || 0;

function CheckIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <path d="M20 6 9 17l-5-5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  );
}

function DownloadIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function ExternalIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 17 17 7" />
      <path d="M7 7h10v10" />
    </svg>
  );
}

function BackIcon() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M19 12H5M12 19l-7-7 7-7" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
      <path d="M5 5l14 14M19 5 5 19" />
    </svg>
  );
}

function PackageIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
      <path d="m3.3 7 8.7 5 8.7-5" />
      <path d="M12 22V12" />
    </svg>
  );
}

function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return (
    <span className={`${styles.badge} ${TONE[tone]}`}>
      <span className={styles.badgeDot} aria-hidden="true" />
      {label}
    </span>
  );
}

export default function OrderDetails({
  order,
  products,
  events,
  courier,
}: {
  order: Order;
  products: OrderItemProducts;
  events: TrackingEvent[];
  courier?: CourierTracking | null;
}) {
  const router = useRouter();
  const { addToCart, pending: cartPending } = useCart();
  const [cancelling, startCancel] = useTransition();
  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [buyingVariant, setBuyingVariant] = useState<string | null>(null);

  const status = orderStatusMeta(order.status);
  const payment = paymentStatusMeta(order.payment_status);
  const address = order.delivery_address;
  const shipment = order.shipment;
  const trackingUrl = safeUrl(courier?.tracking_url ?? shipment?.tracking_url);
  const timeline = buildTimeline(order, events);
  const history = [...events].reverse();
  const unitCount = order.items.reduce((sum, item) => sum + item.quantity, 0);

  const codFee = amount(order.cod_fee);
  const discount = amount(order.discount_amount);
  const advance = amount(order.advance_amount);
  // The backend's total is shown as-is. When prices already include tax the
  // tax line does not add to it, so the label says so instead of implying a sum.
  const added =
    amount(order.subtotal) - discount + amount(order.shipping_amount) + codFee + amount(order.tax_amount);
  const taxIncluded =
    Math.abs(added - amount(order.total_amount)) > 0.005 &&
    Math.abs(added - amount(order.tax_amount) - amount(order.total_amount)) <= 0.005;

  const paymentRef = order.payment?.gateway_payment_id ?? order.payment?.id ?? null;
  const allPayments = order.payments ?? [];

  function confirmCancel() {
    startCancel(async () => {
      const formData = new FormData();
      formData.set('order_id', order.id);
      const result = await cancelOrder(initialCheckoutState, formData);

      if (result.status === 'error') {
        toast.error(result.message ?? 'Could not cancel this order.');
        return;
      }

      toast.info('Order cancelled');
      setCancelModalOpen(false);
      router.refresh();
    });
  }

  async function handleBuyAgain(variantId: string, quantity: number) {
    setBuyingVariant(variantId);
    const error = await addToCart(variantId, quantity);
    setBuyingVariant(null);
    if (error) toast.error(error);
  }

  return (
    <main className={styles.page}>
      <section className={`${homeStyles.container} ${styles.intro}`}>
        <nav className={styles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <Link href="/account/orders">My Orders</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Order #{order.order_number}</span>
        </nav>

        <div className={styles.headerRow}>
          <div className={styles.titleGroup}>
            <h1 className={styles.title}>Order #{order.order_number}</h1>
            <p className={styles.subtitle}>Placed on {formatDate(order.created_at)}</p>
          </div>

          <div className={styles.headerRight}>
            <StatusBadge label={status.label} tone={status.tone} />
            <div className={styles.headerActions}>
              <a href={`/order-details/${order.id}/invoice`} className={styles.solidButton} download>
                <DownloadIcon />
                Download Invoice
              </a>
              {order.can_cancel && (
                <button type="button" className={styles.outlineButton} onClick={() => setCancelModalOpen(true)}>
                  Cancel Order
                </button>
              )}
            </div>
          </div>
        </div>
      </section>

      <section className={`${homeStyles.container} ${styles.content}`}>
        <div className={styles.mainGrid}>
          <div className={styles.leftColumn}>
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>
                Order Items <span className={styles.cardTitleCount}>({unitCount})</span>
              </h2>
              <ul className={styles.itemList}>
                {order.items.map(item => {
                  const product = products[item.product_id];
                  const href = product?.slug
                    ? `/products/${encodeURIComponent(product.slug)}`
                    : `/single-product/${item.product_id}`;
                  const inStock = product?.inStockVariantIds.includes(item.variant_id) ?? false;
                  const itemDiscount = amount(item.discount_amount);

                  return (
                    <li key={item.variant_id} className={styles.itemRow}>
                      <Link href={href} className={styles.itemImage} tabIndex={-1} aria-hidden="true">
                        {product?.image ? (
                          <Image
                            src={mediaUrl(product.image.url)}
                            alt=""
                            fill
                            sizes="96px"
                            className={styles.itemImg}
                          />
                        ) : (
                          <span className={styles.itemImageEmpty}>
                            <PackageIcon />
                          </span>
                        )}
                      </Link>

                      <div className={styles.itemDetails}>
                        <h3 className={styles.itemName}>
                          {product ? <Link href={href}>{item.product_name}</Link> : item.product_name}
                        </h3>
                        {item.variant_name && <p className={styles.itemMeta}>{item.variant_name}</p>}
                        <p className={styles.itemQty}>
                          Qty: {item.quantity}
                          {item.quantity > 1 && ` × ${formatMoney(item.unit_price, order.currency)}`}
                        </p>
                        <p className={styles.itemPrice}>{formatMoney(item.subtotal, order.currency)}</p>
                        {itemDiscount > 0 && (
                          <p className={styles.itemDiscount}>
                            Discount −{formatMoney(item.discount_amount, order.currency)}
                          </p>
                        )}
                      </div>

                      <div className={styles.itemAction}>
                        {product &&
                          (inStock ? (
                            <button
                              type="button"
                              className={styles.outlineButton}
                              disabled={cartPending || buyingVariant !== null}
                              onClick={() => handleBuyAgain(item.variant_id, item.quantity)}>
                              {buyingVariant === item.variant_id ? 'Adding…' : 'Buy Again'}
                            </button>
                          ) : (
                            <span className={styles.itemUnavailable}>Out of stock</span>
                          ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>

            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Order Status</h2>
              <ol className={styles.timeline}>
                {timeline.map(step => (
                  <li
                    key={step.label}
                    className={`${styles.step} ${styles[`step_${step.state}`]}`}
                    aria-current={step.state === 'current' ? 'step' : undefined}>
                    <span className={styles.stepIcon}>
                      {step.state === 'stopped' ? <StopIcon /> : step.state === 'upcoming' ? null : <CheckIcon />}
                    </span>
                    <span className={styles.stepText}>
                      <span className={styles.stepLabel}>{step.label}</span>
                      {step.note && <span className={styles.stepNote}>{step.note}</span>}
                      {step.date && <span className={styles.stepDate}>{formatDate(step.date)}</span>}
                    </span>
                  </li>
                ))}
              </ol>

              {courier && <dl className={styles.shipmentGrid}>
                <div><dt>Courier delivery status</dt><dd>{courier.status_label ?? courier.state.toLowerCase().replaceAll('_', ' ')}</dd></div>
                {courier.provider_etd && !NO_ESTIMATE.includes(order.status) && <div><dt>Courier delivery estimate</dt><dd>{courier.provider_etd}</dd></div>}
                {courier.last_event_at && <div><dt>Last courier update</dt><dd>{formatDateTime(courier.last_event_at)}</dd></div>}
              </dl>}

              {(order.estimated_delivery_date && !courier && !NO_ESTIMATE.includes(order.status)) ||
              shipment?.courier_name ||
              shipment?.tracking_number ||
              order.return_reason ? (
                <dl className={styles.shipmentGrid}>
                  {order.estimated_delivery_date && !courier && !NO_ESTIMATE.includes(order.status) && (
                    <div>
                      <dt>Estimated delivery</dt>
                      <dd>{formatDate(order.estimated_delivery_date)}</dd>
                    </div>
                  )}
                  {shipment?.courier_name && (
                    <div>
                      <dt>Courier</dt>
                      <dd>{shipment.courier_name}</dd>
                    </div>
                  )}
                  {shipment?.tracking_number && (
                    <div>
                      <dt>Tracking number</dt>
                      <dd className={styles.mono}>{shipment.tracking_number}</dd>
                    </div>
                  )}
                  {order.return_reason && (
                    <div>
                      <dt>Return reason</dt>
                      <dd>
                        {order.return_reason}
                        {order.return_note ? ` — ${order.return_note}` : ''}
                      </dd>
                    </div>
                  )}
                </dl>
              ) : null}

              {trackingUrl && (
                <a href={trackingUrl} target="_blank" rel="noopener noreferrer" className={styles.outlineButton}>
                  Track Shipment
                  <ExternalIcon />
                </a>
              )}

              {history.length > 0 && (
                <details className={styles.history}>
                  <summary>Tracking history ({history.length})</summary>
                  <ol>
                    {history.map((event, index) => (
                      <li key={`${event.occurred_at}-${index}`}>
                        <span className={styles.historyText}>
                          {event.description}
                          {event.location && <span className={styles.historyLocation}> · {event.location}</span>}
                        </span>
                        <time dateTime={event.occurred_at}>{formatDateTime(event.occurred_at)}</time>
                      </li>
                    ))}
                  </ol>
                </details>
              )}
            </div>
          </div>

          <aside className={styles.rightColumn}>
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Order Summary</h2>

              <dl className={styles.summary}>
                <div className={styles.summaryRow}>
                  <dt>Subtotal</dt>
                  <dd>{formatMoney(order.subtotal, order.currency)}</dd>
                </div>
                {discount > 0 && (
                  <div className={styles.summaryRow}>
                    <dt>Discount{order.coupon_code ? ` (${order.coupon_code})` : ''}</dt>
                    <dd className={styles.discountValue}>−{formatMoney(order.discount_amount, order.currency)}</dd>
                  </div>
                )}
                <div className={styles.summaryRow}>
                  <dt>Shipping</dt>
                  <dd>
                    {amount(order.shipping_amount) === 0 ? 'Free' : formatMoney(order.shipping_amount, order.currency)}
                  </dd>
                </div>
                {codFee > 0 && (
                  <div className={styles.summaryRow}>
                    <dt>Cash on delivery fee</dt>
                    <dd>{formatMoney(order.cod_fee, order.currency)}</dd>
                  </div>
                )}
                <div className={styles.summaryRow}>
                  <dt>{taxIncluded ? 'Tax (included in prices)' : 'Tax'}</dt>
                  <dd>{formatMoney(order.tax_amount, order.currency)}</dd>
                </div>
                <div className={styles.summaryTotal}>
                  <dt>Total</dt>
                  <dd>{formatMoney(order.total_amount, order.currency)}</dd>
                </div>
                {advance > 0 && (
                  <div className={`${styles.summaryRow} ${styles.summaryNote}`}>
                    <dt>Advance (part of total)</dt>
                    <dd>{formatMoney(order.advance_amount, order.currency)}</dd>
                  </div>
                )}
              </dl>
            </div>
          </aside>

          <div className={styles.infoGrid}>
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Shipping Address</h2>
              <address className={styles.address}>
                <strong>{address.full_name}</strong>
                <span>
                  {address.address_line_1}
                  {address.address_line_2 ? `, ${address.address_line_2}` : ''}
                </span>
                <span>
                  {address.city}, {address.state} {address.postal_code}
                </span>
                <span>{address.country}</span>
                {address.phone && <span>Phone: {address.phone}</span>}
                {order.contact_email && <span>{order.contact_email}</span>}
              </address>
            </div>

            <div className={styles.card}>
              <div className={styles.cardHeader}>
                <h2 className={styles.cardTitle}>Payment Information</h2>
                <StatusBadge label={payment.label} tone={payment.tone} />
              </div>
              <dl className={styles.paymentGrid}>
                <div className={styles.paymentWide}>
                  <dt>Payment method</dt>
                  <dd>{paymentMethodLabel(order)}</dd>
                </div>
                <div>
                  <dt>Order ID</dt>
                  <dd>{order.order_number}</dd>
                </div>
                {paymentRef && (
                  <div>
                    <dt>Payment ID</dt>
                    <dd className={styles.mono}>{paymentRef}</dd>
                  </div>
                )}
              </dl>

              {allPayments.length > 1 && (
                <ul className={styles.paymentList}>
                  {allPayments.map(entry => {
                    const meta = paymentStatusMeta(entry.status);
                    return (
                      <li key={entry.id}>
                        <span>
                          {PROVIDER_LABELS[entry.provider] ?? entry.provider} ·{' '}
                          {formatMoney(entry.amount, entry.currency)}
                        </span>
                        <StatusBadge label={meta.label} tone={meta.tone} />
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          </div>
        </div>

        <div className={styles.backRow}>
          <Link href="/account/orders" className={styles.outlineButton}>
            <BackIcon />
            Back to My Orders
          </Link>
        </div>
      </section>

      {cancelModalOpen && (
        <div className={styles.cancelOverlay} onClick={() => !cancelling && setCancelModalOpen(false)}>
          <div
            className={styles.cancelModal}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-order-title"
            onClick={event => event.stopPropagation()}>
            <button
              type="button"
              className={styles.cancelClose}
              aria-label="Close"
              disabled={cancelling}
              onClick={() => setCancelModalOpen(false)}>
              <CloseIcon />
            </button>

            <h2 id="cancel-order-title" className={styles.cancelTitle}>
              Cancel order #{order.order_number}?
            </h2>
            <p className={styles.cancelSubtitle}>This can&apos;t be undone.</p>

            <ul className={styles.cancelItems}>
              {order.items.map(item => (
                <li key={item.variant_id}>
                  <span>
                    {item.product_name}
                    <small>
                      {item.variant_name} · Qty {item.quantity}
                    </small>
                  </span>
                  <span>{formatMoney(item.subtotal, order.currency)}</span>
                </li>
              ))}
            </ul>

            <div className={styles.cancelActions}>
              <button
                type="button"
                className={styles.outlineButton}
                disabled={cancelling}
                onClick={() => setCancelModalOpen(false)}>
                Keep Order
              </button>
              <button type="button" className={styles.solidButton} disabled={cancelling} onClick={confirmCancel}>
                {cancelling ? 'Cancelling…' : 'Yes, Cancel'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
