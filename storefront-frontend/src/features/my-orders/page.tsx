import { redirect } from 'next/navigation';

import MobileBottomNav from '@/components/luxe/MobileBottomNav';
import { catalogueApi } from '@/lib/api/catalogue';
import { ApiError } from '@/lib/api/errors';
import { orderApi } from '@/lib/api/orders';
import { getAccessToken } from '@/lib/auth/session';
import { signInUrl } from '@/lib/auth/sign-in-url';
import { ORDER_FILTERS } from '@/lib/orders/status';
import type { OrderSummary } from '@/types/orders';

import MyOrders, { type OrderItemImage, type OrderRow } from './_components/MyOrders';

export const metadata = {
  title: 'My Orders | CliQ.',
};

const PAGE_SIZE = 10;
/** The backend's page size cap. */
const FETCH_SIZE = 100;

type SearchParams = { status?: string; q?: string; page?: string };

/**
 * Every order the customer has, newest first.
 *
 * `GET /orders` takes only page controls -- no status filter and no search --
 * so the customer's summaries are read in full (they are small, and a
 * customer's history is short) and the tabs, order-number search and paging
 * are applied here. Only the orders on the visible page are then expanded:
 *
 *  - `GET /orders/{id}` for the real lines (item count, which products)
 *  - `GET /storefront/products/{id}` for the first product's primary image,
 *    deduplicated across the page
 *
 * The order list endpoint carries no images, which is why the second step
 * exists at all.
 */
async function loadAllSummaries(token: string): Promise<OrderSummary[]> {
  const first = await orderApi.list(token, { page: 1, page_size: FETCH_SIZE });
  const rest = await Promise.all(
    Array.from({ length: Math.max(0, first.meta.total_pages - 1) }, (_, index) =>
      orderApi.list(token, { page: index + 2, page_size: FETCH_SIZE }),
    ),
  );
  return [first, ...rest].flatMap(page => page.items);
}

async function expand(token: string, summaries: OrderSummary[]): Promise<OrderRow[]> {
  const details = await Promise.all(summaries.map(summary => orderApi.get(token, summary.id).catch(() => null)));

  const productIds = Array.from(
    new Set(
      details.flatMap(detail => (detail?.items[0] ? [detail.items[0].product_id] : [])),
    ),
  );

  const images = new Map<string, OrderItemImage>();
  await Promise.all(
    productIds.map(async productId => {
      const product = await catalogueApi.getProduct(productId).catch(() => null);
      const primary = product?.images.find(image => image.is_primary) ?? product?.images[0] ?? null;
      if (primary) images.set(productId, { url: primary.url, alt_text: primary.alt_text ?? product?.name ?? null });
    }),
  );

  return summaries.map((summary, index) => {
    const detail = details[index];
    if (!detail) return { ...summary, item_count: null, product_count: 0, preview_image: null };

    const first = detail.items[0]?.product_id;
    return {
      ...summary,
      item_count: detail.items.reduce((sum, item) => sum + item.quantity, 0),
      product_count: new Set(detail.items.map(item => item.product_id)).size,
      preview_image: first ? (images.get(first) ?? null) : null,
    };
  });
}

export default async function MyOrdersPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;

  const token = await getAccessToken();
  if (!token) redirect(signInUrl('/account/orders'));

  let summaries: OrderSummary[];
  try {
    summaries = await loadAllSummaries(token);
  } catch (error) {
    if (error instanceof ApiError && error.isUnauthenticated) redirect(signInUrl('/account/orders'));
    return (
      <>
        <MyOrders state={{ kind: 'error' }} />
        <MobileBottomNav />
      </>
    );
  }

  const filter = ORDER_FILTERS.find(f => f.value === params.status) ?? null;
  const query = (params.q ?? '').trim();
  const needle = query.toUpperCase().replace(/^#/, '');

  const counts: Record<string, number> = { all: summaries.length };
  for (const f of ORDER_FILTERS) {
    counts[f.value] = summaries.filter(order => f.statuses.includes(order.status)).length;
  }

  const matching = summaries.filter(
    order =>
      (!filter || filter.statuses.includes(order.status)) &&
      (!needle || order.order_number.toUpperCase().includes(needle)),
  );

  const totalPages = Math.max(1, Math.ceil(matching.length / PAGE_SIZE));
  const requested = Number.parseInt(params.page ?? '1', 10);
  const page = Number.isFinite(requested) ? Math.min(Math.max(requested, 1), totalPages) : 1;

  const rows = await expand(token, matching.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE));

  return (
    <>
      <MyOrders
        state={{
          kind: 'ready',
          orders: rows,
          totalOrders: summaries.length,
          matchingOrders: matching.length,
          counts,
          status: filter?.value ?? 'all',
          query,
          page,
          totalPages,
        }}
      />
      <MobileBottomNav />
    </>
  );
}
