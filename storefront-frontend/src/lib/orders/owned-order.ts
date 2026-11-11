import { notFound, redirect } from 'next/navigation';

import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';

/** Resolve a public order number only within the signed-in customer's orders. */
export async function resolveOwnedOrderId(orderNumber: string, destination: string): Promise<string> {
  const token = await getAccessToken();
  if (!token) redirect(signInUrl(destination));

  const firstPage = await orderApi.list(token, { page: 1, page_size: 100 });
  const pages = await Promise.all(
    Array.from({ length: Math.max(0, firstPage.meta.total_pages - 1) }, (_, index) =>
      orderApi.list(token, { page: index + 2, page_size: 100 }),
    ),
  );
  const summary = [firstPage, ...pages]
    .flatMap(page => page.items)
    .find(order => order.order_number === orderNumber);

  if (!summary) notFound();
  return summary.id;
}
