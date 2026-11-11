import { notFound, redirect } from 'next/navigation';

import MobileBottomNav from '@/components/luxe/MobileBottomNav';
import { catalogueApi } from '@/lib/api/catalogue';
import { ApiError } from '@/lib/api/errors';
import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';
import type { Order } from '@/types/orders';

import OrderDetails, { type OrderItemProducts } from '../_components/OrderDetails';
import OrderLoadError from '../_components/OrderLoadError';

/** Order ids are UUIDs; anything else cannot be an order and is answered without an API call. */
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * One order, in full, from `GET /orders/{id}` -- the backend only returns
 * the signed-in customer's own orders, so another customer's id is a 404.
 *
 * Alongside it, all read-only and best-effort:
 *  - `GET /orders/{id}/tracking` for the recorded status history, which is
 *    what dates the timeline steps (the order itself only has created_at)
 *  - `GET /storefront/products/{id}` per distinct product, for its image
 *    and whether the ordered variant can still be bought
 */
export default async function OrderDetailsPage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  if (!UUID.test(orderId)) notFound();

  const token = await getAccessToken();
  if (!token) redirect(signInUrl(`/order-details/${orderId}`));

  let order: Order;
  try {
    order = await orderApi.get(token, orderId);
  } catch (error) {
    if (error instanceof ApiError && (error.isNotFound || error.isForbidden)) notFound();
    if (error instanceof ApiError && error.isUnauthenticated) redirect(signInUrl(`/order-details/${orderId}`));
    return <OrderLoadError />;
  }

  const productIds = Array.from(new Set(order.items.map(item => item.product_id)));

  const [tracking, products] = await Promise.all([
    orderApi.tracking(token, order.id).catch(() => null),
    Promise.all(productIds.map(id => catalogueApi.getProduct(id).catch(() => null))),
  ]);

  const catalogue: OrderItemProducts = {};
  productIds.forEach((productId, index) => {
    const product = products[index];
    if (!product) return;
    const primary = product.images.find(image => image.is_primary) ?? product.images[0] ?? null;
    catalogue[productId] = {
      image: primary ? { url: primary.url, alt_text: primary.alt_text } : null,
      slug: product.slug ?? null,
      inStockVariantIds: product.variants.filter(variant => variant.in_stock).map(variant => variant.id),
    };
  });

  return (
    <>
      <OrderDetails order={order} products={catalogue} events={tracking?.events ?? []} courier={tracking?.courier ?? null} />
      <MobileBottomNav />
    </>
  );
}
