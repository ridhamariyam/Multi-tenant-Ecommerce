import InvoicePage from '../../../../../(invoice)/invoice/[orderId]/page';
import { resolveOwnedOrderId } from '@/lib/orders/owned-order';

export default async function AccountOrderInvoicePage({ params }: { params: Promise<{ orderNumber: string }> }) {
  const { orderNumber } = await params;
  const orderId = await resolveOwnedOrderId(
    orderNumber,
    `/account/orders/${orderNumber}/invoice`,
  );
  return <InvoicePage params={Promise.resolve({ orderId })} />;
}
