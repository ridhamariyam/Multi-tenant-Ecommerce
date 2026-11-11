import type { OrderStatus, PaymentStatus } from '@/types/orders';

/** Badge colour family; each page maps it onto its own CSS module classes. */
export type StatusTone = 'amber' | 'blue' | 'green' | 'red' | 'neutral';

export const ORDER_STATUS_META: Record<OrderStatus, { label: string; tone: StatusTone }> = {
  PENDING: { label: 'Pending', tone: 'amber' },
  CONFIRMED: { label: 'Confirmed', tone: 'blue' },
  PROCESSING: { label: 'Processing', tone: 'blue' },
  PACKED: { label: 'Packed', tone: 'blue' },
  SHIPPED: { label: 'Shipped', tone: 'blue' },
  OUT_FOR_DELIVERY: { label: 'Out for delivery', tone: 'blue' },
  DELIVERED: { label: 'Delivered', tone: 'green' },
  CANCELLED: { label: 'Cancelled', tone: 'red' },
  RETURN_REQUESTED: { label: 'Return requested', tone: 'amber' },
  RETURNED: { label: 'Returned', tone: 'neutral' },
  REFUNDED: { label: 'Refunded', tone: 'neutral' },
};

export const PAYMENT_STATUS_META: Record<PaymentStatus, { label: string; tone: StatusTone }> = {
  PENDING: { label: 'Pending', tone: 'amber' },
  PARTIALLY_PAID: { label: 'Partially paid', tone: 'amber' },
  PAID: { label: 'Paid', tone: 'green' },
  FAILED: { label: 'Failed', tone: 'red' },
  REFUNDED: { label: 'Refunded', tone: 'blue' },
};

/** Falls back to the raw value, so a status added on the backend later still renders. */
export function orderStatusMeta(status: string): { label: string; tone: StatusTone } {
  return ORDER_STATUS_META[status as OrderStatus] ?? { label: status, tone: 'neutral' };
}

export function paymentStatusMeta(status: string): { label: string; tone: StatusTone } {
  return PAYMENT_STATUS_META[status as PaymentStatus] ?? { label: status, tone: 'neutral' };
}

/**
 * The My Orders tabs. The customer listing endpoint takes no status filter,
 * so each tab groups the backend statuses it covers and is applied to the
 * customer's own rows. PACKED reads as processing and OUT_FOR_DELIVERY as
 * shipped, the way a shopper would describe them.
 */
export const ORDER_FILTERS: { value: string; label: string; statuses: readonly OrderStatus[] }[] = [
  { value: 'pending', label: 'Pending', statuses: ['PENDING'] },
  { value: 'confirmed', label: 'Confirmed', statuses: ['CONFIRMED'] },
  { value: 'processing', label: 'Processing', statuses: ['PROCESSING', 'PACKED'] },
  { value: 'shipped', label: 'Shipped', statuses: ['SHIPPED', 'OUT_FOR_DELIVERY'] },
  { value: 'delivered', label: 'Delivered', statuses: ['DELIVERED'] },
  { value: 'cancelled', label: 'Cancelled', statuses: ['CANCELLED'] },
  { value: 'returned', label: 'Returned', statuses: ['RETURN_REQUESTED', 'RETURNED', 'REFUNDED'] },
];

/** The forward lifecycle shown on the order timeline. */
export const ORDER_STEPS: { label: string; statuses: readonly OrderStatus[] }[] = [
  { label: 'Order Placed', statuses: ['PENDING'] },
  { label: 'Confirmed', statuses: ['CONFIRMED'] },
  { label: 'Processing', statuses: ['PROCESSING', 'PACKED'] },
  { label: 'Shipped', statuses: ['SHIPPED', 'OUT_FOR_DELIVERY'] },
  { label: 'Delivered', statuses: ['DELIVERED'] },
];

/** Index into ORDER_STEPS the status has reached, or -1 off the forward line. */
export function orderStepIndex(status: OrderStatus): number {
  return ORDER_STEPS.findIndex(step => step.statuses.includes(status));
}
