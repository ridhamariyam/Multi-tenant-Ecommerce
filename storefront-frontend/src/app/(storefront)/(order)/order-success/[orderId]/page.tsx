import { notFound, redirect } from 'next/navigation';

import { ApiError } from '@/lib/api/errors';
import { catalogueApi } from '@/lib/api/catalogue';
import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';
import type { Order } from '@/types/orders';
import OrderSuccess from '../_components/OrderSuccess';
import OrderLoadError from '@/app/(storefront)/(order-details)/order-details/_components/OrderLoadError';

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export default async function OrderSuccessPage({ params }: { params: Promise<{ orderId: string }> }) {
  const { orderId } = await params;
  if (!UUID.test(orderId)) notFound();

  const token = await getAccessToken();
  if (!token) redirect(signInUrl(`/order-details/${orderId}`));

  let order: Order;

  try {
    order = await orderApi.get(token, orderId);
  } catch (error) {
    /* Someone else's order reads as 403; either way there is nothing to show. */
    if (error instanceof ApiError && (error.isNotFound || error.isForbidden)) notFound();
    if (error instanceof ApiError && error.isUnauthenticated) redirect(signInUrl(`/order-details/${orderId}`));
    return <OrderLoadError />;
  }

  const productIds = Array.from(new Set(order.items.map(item => item.product_id)));
  const products = await Promise.all(productIds.map(id => catalogueApi.getProduct(id).catch(() => null)));
  const productImages: Record<string, { url: string; alt_text: string | null } | null> = {};
  productIds.forEach((id, index) => {
    const product = products[index];
    const image = product?.images.find(candidate => candidate.is_primary) ?? product?.images[0] ?? null;
    productImages[id] = image ? { url: image.url, alt_text: image.alt_text } : null;
  });

  return <OrderSuccess order={order} productImages={productImages} />;
}
