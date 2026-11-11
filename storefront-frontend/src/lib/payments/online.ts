import {
  PAYMENT_METHOD_LABELS,
  type OnlinePaymentRequest,
  type Order,
  type PaymentMethod,
  type PaymentProvider,
} from '@/types/orders';

const PROVIDER_LABELS: Record<PaymentProvider, string> = {
  COD: 'Cash on Delivery',
  PREPAID: 'Prepaid',
  RAZORPAY: 'Paid Online',
};

/** How the shopper chose to pay, for display: "UPI", "Cash on Delivery"... */
export function paymentMethodLabel(order: Order): string {
  if (order.payment_method) return PAYMENT_METHOD_LABELS[order.payment_method] ?? order.payment_method;
  if (!order.payment) return '—';
  return PROVIDER_LABELS[order.payment.provider] ?? order.payment.provider;
}

/**
 * The Razorpay payment this order is still waiting on, ready to open
 * Checkout with -- or null when there is nothing to pay online.
 *
 * The backend creates the Razorpay order when the order is placed, so
 * everything needed is already on the order: no extra call, and reopening
 * Checkout after the shopper closed it pays against the same Razorpay order.
 */
export function pendingOnlinePayment(order: Order): OnlinePaymentRequest | null {
  if (order.status === 'CANCELLED') return null;

  const payments = order.payments?.length ? order.payments : order.payment ? [order.payment] : [];
  const payment = payments.find(
    candidate => candidate.provider === 'RAZORPAY' && candidate.status === 'PENDING' && candidate.gateway_order_id,
  );
  if (!payment?.gateway_order_id) return null;

  return {
    orderId: order.id,
    orderNumber: order.order_number,
    razorpayOrderId: payment.gateway_order_id,
    amount: Math.round(Number(payment.amount) * 100),
    currency: payment.currency,
    method: order.payment_method ?? 'UPI',
    name: order.delivery_address.full_name,
    contact: order.delivery_address.phone,
  };
}

/** Razorpay Checkout's own name for a method, used to open it on that tab. */
export function razorpayMethod(method: PaymentMethod): 'upi' | 'card' | 'netbanking' | undefined {
  switch (method) {
    case 'UPI':
      return 'upi';
    case 'CREDIT_CARD':
    case 'DEBIT_CARD':
      return 'card';
    case 'NET_BANKING':
      return 'netbanking';
    default:
      return undefined;
  }
}
