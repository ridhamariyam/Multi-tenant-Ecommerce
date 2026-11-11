import { unstable_rethrow } from 'next/navigation';

import OrderDetailsPage from '../../../../(order-details)/order-details/[orderId]/page';
import OrderLoadError from '../../../../(order-details)/order-details/_components/OrderLoadError';
import { resolveOwnedOrderId } from '@/lib/orders/owned-order';

export default async function AccountOrderPage({ params }: { params: Promise<{ orderNumber: string }> }) {
  const { orderNumber } = await params;

  let orderId: string;
  try {
    orderId = await resolveOwnedOrderId(orderNumber, `/account/orders/${orderNumber}`);
  } catch (error) {
    // Sign-in redirects and "not one of yours" 404s pass through; anything else is the API failing.
    unstable_rethrow(error);
    return <OrderLoadError />;
  }

  return <OrderDetailsPage params={Promise.resolve({ orderId })} />;
}
