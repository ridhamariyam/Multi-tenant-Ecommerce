import ProtectedRoute from '@/components/ProtectedRoute';
import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import PaymentHistory, { type PaymentRow } from './_components/PaymentHistory';

/** How many orders deep the payment table goes. */
const HISTORY_LIMIT = 20;

/**
 * Payment history, assembled from orders.
 *
 * The backend has no customer payment listing -- /payments only looks one
 * up by id -- and the order list carries no payment, so each order is read
 * for the payment hanging off it. Capped, because that is one call per row.
 */
async function loadPayments(token: string): Promise<PaymentRow[]> {
  const page = await orderApi.list(token, { page_size: HISTORY_LIMIT });

  const orders = await Promise.all(
    page.items.map(summary => orderApi.get(token, summary.id).catch(() => null)),
  );

  return orders.filter(order => order !== null).map(order => ({
    orderId: order.id,
    orderNumber: order.order_number,
    paymentId: order.payment ? order.payment.id : '—',
    method: order.payment ? order.payment.provider : 'Cash on delivery',
    amount: order.payment ? order.payment.amount : order.total_amount,
    currency: order.currency,
    status: order.payment_status,
  }));
}

export default async function PaymentHistoryPage() {
  const token = await getAccessToken();
  const payments = token ? await loadPayments(token) : [];

  return (
    <>
      <ProtectedRoute>
        <PaymentHistory payments={payments} />
      </ProtectedRoute>
    </>
  );
}
