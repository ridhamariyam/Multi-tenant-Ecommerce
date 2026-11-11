'use client';

import { useState } from 'react';

import { formatDate, formatDateTime } from '@/lib/format';
import { trackOrder } from '@/lib/orders/guest-actions';
import type { OrderTracking } from '@/types/orders';

import styles from './TrackOrder.module.css';

/** "OUT_FOR_DELIVERY" -> "Out for delivery". */
function label(status: string): string {
  const words = status.toLowerCase().replace(/_/g, ' ');
  return words.charAt(0).toUpperCase() + words.slice(1);
}

export default function TrackOrderForm({ initialOrderNumber }: { initialOrderNumber: string }) {
  const [orderNumber, setOrderNumber] = useState(initialOrderNumber);
  const [phone, setPhone] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tracking, setTracking] = useState<OrderTracking | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);
    setError(null);
    const result = await trackOrder(orderNumber, phone);
    setPending(false);
    setTracking(result.tracking);
    setError(result.error);
  }

  const events = tracking ? [...tracking.events].reverse() : [];

  return (
    <>
      <form onSubmit={submit} className={styles.form}>
        <label className={styles.field}>
          <span>Order number</span>
          <input
            value={orderNumber}
            onChange={event => setOrderNumber(event.target.value)}
            required
            maxLength={32}
            autoComplete="off"
            placeholder="e.g. ORD-2026-000123"
          />
        </label>
        <label className={styles.field}>
          <span>Mobile number</span>
          <input
            value={phone}
            onChange={event => setPhone(event.target.value)}
            required
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            maxLength={16}
            placeholder="10-digit mobile number"
          />
        </label>
        <button type="submit" className={styles.button} disabled={pending}>
          {pending ? 'Looking up…' : 'Track order'}
        </button>
      </form>

      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}

      {tracking && (
        <section className={styles.result} aria-live="polite">
          <p className={styles.number}>Order {tracking.order_number}</p>
          <p className={styles.status}>{tracking.courier?.status_label ?? label(tracking.status)}</p>
          {tracking.estimated_delivery_date && (
            <p className={styles.meta}>Estimated delivery: {formatDate(tracking.estimated_delivery_date)}</p>
          )}
          {tracking.shipment.tracking_number && (
            <p className={styles.meta}>
              {tracking.shipment.courier_name ?? 'Courier'} · {tracking.shipment.tracking_number}
              {tracking.shipment.tracking_url && (
                <>
                  {' · '}
                  <a href={tracking.shipment.tracking_url} target="_blank" rel="noopener noreferrer">
                    Courier tracking
                  </a>
                </>
              )}
            </p>
          )}
          {events.length > 0 && (
            <ol className={styles.events}>
              {events.map(event => (
                <li key={`${event.occurred_at}-${event.description}`}>
                  <strong>{event.description}</strong>
                  <span>
                    {formatDateTime(event.occurred_at)}
                    {event.location ? ` · ${event.location}` : ''}
                  </span>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </>
  );
}
