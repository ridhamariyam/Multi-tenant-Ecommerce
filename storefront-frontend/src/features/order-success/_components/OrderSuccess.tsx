import Image from 'next/image';
import Link from 'next/link';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { formatDate, formatMoney } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import { orderStatusMeta, paymentStatusMeta } from '@/lib/orders/status';
import { paymentMethodLabel, pendingOnlinePayment } from '@/lib/payments/online';
import type { Order } from '@/types/orders';

import styles from './OrderSuccess.module.css';
import PayNowButton from './PayNowButton';

export type OrderProductImages = Record<string, { url: string; alt_text: string | null } | null | undefined>;

function StatusIcon({ state }: { state: 'success' | 'pending' | 'failed' }) {
  return (
    <span className={`${styles.statusIcon} ${state === 'failed' ? styles.statusIconFailed : ''} ${state === 'pending' ? styles.statusIconPending : ''}`} aria-hidden="true">
      {state === 'failed' ? (
        <svg viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="21" stroke="currentColor" strokeWidth="2" />
          <path d="m17 17 14 14m0-14L17 31" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" />
        </svg>
      ) : state === 'pending' ? (
        <svg viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="21" stroke="currentColor" strokeWidth="2" />
          <path d="M24 12v13l8 5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ) : (
        <svg viewBox="0 0 48 48" fill="none">
          <circle cx="24" cy="24" r="21" stroke="currentColor" strokeWidth="2" />
          <path d="M15 24.5 21 30.5 33 17.5" stroke="currentColor" strokeWidth="2.3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )}
    </span>
  );
}

function ArrowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M4 12h16M13 5l7 7-7 7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function OrderSuccess({ order, productImages }: { order: Order; productImages: OrderProductImages }) {
  const pendingPayment = pendingOnlinePayment(order);
  const paymentFailed = order.payment_status === 'FAILED';
  const stopped = ['CANCELLED', 'RETURN_REQUESTED', 'RETURNED', 'REFUNDED'].includes(order.status);
  const isCashOrder = order.payment_method === 'CASH_ON_DELIVERY' || order.payment?.provider === 'COD';
  const paymentRecorded = order.payment_status === 'PAID' || order.payment_status === 'PARTIALLY_PAID';
  const orderPlaced = !stopped && !paymentFailed && (isCashOrder || paymentRecorded);
  const confirmed = orderPlaced && order.status !== 'PENDING';
  const waitingForPayment = !isCashOrder && order.payment_status === 'PENDING' && !stopped;
  const heading = stopped
    ? orderStatusMeta(order.status).label
    : paymentFailed
      ? 'Payment not completed'
      : waitingForPayment
        ? 'Payment confirmation pending'
        : confirmed
          ? 'Your order is confirmed'
          : isCashOrder
            ? 'Order placed'
            : 'Payment received';
  const message = stopped
    ? `This order is ${orderStatusMeta(order.status).label.toLowerCase()}. View the order details for its latest status.`
    : paymentFailed
      ? 'We could not confirm your payment. Your order details remain available; please check the payment status before trying again.'
      : waitingForPayment
        ? 'Your order has been saved, but we have not received payment confirmation yet. Please do not pay again if your account was charged.'
        : confirmed
          ? 'Thank you for choosing CliQ. We’ll keep you updated as your order moves through delivery.'
          : isCashOrder
            ? 'Your Cash on Delivery order has been received and is awaiting order confirmation.'
            : 'Your payment is recorded. The order is awaiting confirmation; check its details for the latest status.';
  const orderHref = `/account/orders/${encodeURIComponent(order.order_number)}`;
  const invoiceHref = `/account/invoices/${encodeURIComponent(order.id)}/pdf`;
  const address = order.delivery_address;

  return (
    <main className={styles.page}>
      <div className={`${homeStyles.container} ${styles.container}`}>
        <nav className={styles.breadcrumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link><span aria-hidden="true">/</span><Link href="/account/orders">My Orders</Link>
          <span aria-hidden="true">/</span><span aria-current="page">{confirmed ? 'Order confirmed' : 'Order status'}</span>
        </nav>

        <section className={styles.hero}>
          <StatusIcon state={confirmed ? 'success' : paymentFailed || stopped ? 'failed' : 'pending'} />
          <p className={styles.eyebrow}>{confirmed ? 'Thank you for your order' : 'Order update'}</p>
          <h1 className={styles.heading}>{heading}</h1>
          <p className={styles.message}>{message}</p>
          <div className={styles.orderMeta}>
            <span>Order <strong>#{order.order_number}</strong></span>
            <span>{formatDate(order.created_at)}</span>
            <span className={styles.statusBadge}>{paymentStatusMeta(order.payment_status).label}</span>
          </div>
        </section>

        <div className={styles.contentGrid}>
          <section className={styles.panel} aria-labelledby="items-heading">
            <div className={styles.panelHeader}>
              <h2 id="items-heading" className={styles.panelTitle}>Items in this order</h2>
              <span className={styles.itemCount}>{order.items.reduce((count, item) => count + item.quantity, 0)} items</span>
            </div>
            <ul className={styles.itemList}>
              {order.items.map(item => {
                const image = productImages[item.product_id];
                const src = mediaUrl(image?.url);
                return (
                  <li className={styles.item} key={item.variant_id}>
                    <div className={styles.imageBox}>
                      {src ? <Image src={src} alt={image?.alt_text ?? item.product_name} fill sizes="(max-width: 640px) 72px, 88px" /> : <span className={styles.imagePlaceholder}>CliQ.</span>}
                    </div>
                    <div className={styles.itemDetails}>
                      <h3>{item.product_name}</h3>
                      <p>{item.variant_name}</p>
                      <p>Qty {item.quantity} <span aria-hidden="true">·</span> {formatMoney(item.unit_price, order.currency)} each</p>
                    </div>
                    <strong className={styles.itemTotal}>{formatMoney(item.subtotal, order.currency)}</strong>
                  </li>
                );
              })}
            </ul>
            {order.estimated_delivery_date && (
              <p className={styles.deliveryEstimate}>Estimated delivery <strong>{formatDate(order.estimated_delivery_date)}</strong></p>
            )}
          </section>

          <aside className={styles.sideColumn}>
            <section className={`${styles.panel} ${styles.summary}`} aria-labelledby="summary-heading">
              <h2 id="summary-heading" className={styles.panelTitle}>Order summary</h2>
              <dl className={styles.totals}>
                <div><dt>Subtotal</dt><dd>{formatMoney(order.subtotal, order.currency)}</dd></div>
                {Number(order.discount_amount) > 0 && <div><dt>Discount{order.coupon_code ? ` · ${order.coupon_code}` : ''}</dt><dd>−{formatMoney(order.discount_amount, order.currency)}</dd></div>}
                <div><dt>Shipping</dt><dd>{Number(order.shipping_amount) === 0 ? 'Free' : formatMoney(order.shipping_amount, order.currency)}</dd></div>
                {Number(order.cod_fee ?? 0) > 0 && <div><dt>Cash handling</dt><dd>{formatMoney(order.cod_fee, order.currency)}</dd></div>}
                <div><dt>Tax</dt><dd>{formatMoney(order.tax_amount, order.currency)}</dd></div>
                <div className={styles.grandTotal}><dt>Total</dt><dd>{formatMoney(order.total_amount, order.currency)}</dd></div>
              </dl>
              <div className={styles.paymentInfo}>
                <span>Payment method</span><strong>{paymentMethodLabel(order)}</strong>
                <span>Payment status</span><strong>{paymentStatusMeta(order.payment_status).label}</strong>
              </div>
            </section>

            <section className={`${styles.panel} ${styles.address}`} aria-labelledby="address-heading">
              <h2 id="address-heading" className={styles.panelTitle}>Delivery address</h2>
              <address>
                <strong>{address.full_name}</strong>
                <span>{address.address_line_1}{address.address_line_2 ? `, ${address.address_line_2}` : ''}</span>
                <span>{address.city}, {address.state} {address.postal_code}</span>
                <span>{address.country}</span>
                <span>{address.phone}</span>
              </address>
            </section>
          </aside>
        </div>

        <nav className={styles.actions} aria-label="Order actions">
          {waitingForPayment && pendingPayment && <PayNowButton request={pendingPayment} className={styles.primaryButton} />}
          <Link href={orderHref} className={waitingForPayment && pendingPayment ? styles.outlineButton : styles.primaryButton}>
            View Order Details <ArrowIcon />
          </Link>
          <Link href={invoiceHref} className={styles.outlineButton}>Download Invoice</Link>
          <Link href="/products" className={styles.textButton}>Continue Shopping</Link>
        </nav>
      </div>
    </main>
  );
}
