import OrderSuccessPage from '../../../(order)/order-success/[orderId]/page';
import { resolveOwnedOrderId } from '@/lib/orders/owned-order';

export default async function OrderConfirmationPage({ params }: { params: Promise<{ orderNumber: string }> }) {
  const { orderNumber } = await params;
  const orderId = await resolveOwnedOrderId(orderNumber, `/order-confirmation/${orderNumber}`);
  return <OrderSuccessPage params={Promise.resolve({ orderId })} />;
}
