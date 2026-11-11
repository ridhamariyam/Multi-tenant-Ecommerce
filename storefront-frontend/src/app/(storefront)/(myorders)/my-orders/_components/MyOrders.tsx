import Image from 'next/image';
import Link from 'next/link';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { formatDate, formatMoney } from '@/lib/format';
import { mediaUrl } from '@/lib/media';
import { ORDER_FILTERS, orderStatusMeta } from '@/lib/orders/status';
import type { OrderSummary } from '@/types/orders';

import styles from './MyOrders.module.css';

export interface OrderItemImage {
  url: string;
  alt_text: string | null;
}

/**
 * `OrderSummary` is the real `/orders` row -- no items, no image (see
 * `page.tsx`). The extra fields are read from each order's own detail and
 * its first product, so they live on this page-local type and the shared
 * `OrderSummary` stays an honest match for the wire response.
 */
export interface OrderRow extends OrderSummary {
  /** Units across every line, or null when the order's detail could not be read. */
  item_count: number | null;
  /** Distinct products; more than one shows as "+N" on the thumbnail. */
  product_count: number;
  preview_image: OrderItemImage | null;
}

export type MyOrdersState =
  | { kind: 'error' }
  | {
      kind: 'ready';
      orders: OrderRow[];
      totalOrders: number;
      matchingOrders: number;
      counts: Record<string, number>;
      status: string;
      query: string;
      page: number;
      totalPages: number;
    };

const TONE_DOT: Record<string, string> = {
  amber: styles.dotAmber,
  blue: styles.dotBlue,
  green: styles.dotGreen,
  red: styles.dotRed,
  neutral: styles.dotNeutral,
};

const TABS = [{ value: 'all', label: 'All' }, ...ORDER_FILTERS];

/** A link to this same page with the listing controls changed; relative, so it works at both order URLs. */
function listingHref(status: string, query: string, page = 1): string {
  const params = new URLSearchParams();
  if (status !== 'all') params.set('status', status);
  if (query) params.set('q', query);
  if (page > 1) params.set('page', String(page));
  const qs = params.toString();
  return qs ? `?${qs}` : '?';
}

function PackageIcon() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16Z" />
      <path d="m3.3 7 8.7 5 8.7-5" />
      <path d="M12 22V12" />
    </svg>
  );
}

function ArrowUpRightIcon() {
  return (
    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M7 17 17 7" />
      <path d="M7 7h10v10" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden="true">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-3.5-3.5" />
    </svg>
  );
}

function Intro() {
  return (
    <section className={`${homeStyles.container} ${styles.intro}`}>
      <nav className={styles.crumb} aria-label="Breadcrumb">
        <Link href="/">Home</Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">My Orders</span>
      </nav>
      <h1 className={styles.title}>My Orders</h1>
      <p className={styles.description}>Track and manage your orders.</p>
    </section>
  );
}

function OrderCard({ order }: { order: OrderRow }) {
  const meta = orderStatusMeta(order.status);
  const href = `/account/orders/${encodeURIComponent(order.order_number)}`;
  const moreProducts = order.product_count - 1;

  return (
    <article className={styles.card}>
      <Link href={href} className={styles.thumb} tabIndex={-1} aria-hidden="true">
        {order.preview_image ? (
          <Image
            src={mediaUrl(order.preview_image.url)}
            alt=""
            fill
            sizes="(max-width: 749px) 76px, 104px"
            className={styles.thumbImg}
          />
        ) : (
          <span className={styles.thumbEmpty}>
            <PackageIcon />
          </span>
        )}
        {moreProducts > 0 && <span className={styles.thumbMore}>+{moreProducts}</span>}
      </Link>

      <div className={styles.body}>
        <div className={styles.top}>
          <div className={styles.heading}>
            <h2 className={styles.number}>Order #{order.order_number}</h2>
            <p className={styles.meta}>
              Placed on {formatDate(order.created_at)}
              {order.item_count !== null && ` · ${order.item_count} ${order.item_count === 1 ? 'item' : 'items'}`}
            </p>
          </div>
          <span className={styles.status}>
            <span className={`${styles.dot} ${TONE_DOT[meta.tone]}`} aria-hidden="true" />
            {meta.label}
          </span>
        </div>

        <div className={styles.bottom}>
          <p className={styles.amount}>{formatMoney(order.total_amount, order.currency)}</p>
          <Link href={href} className={styles.viewButton} aria-label={`View order #${order.order_number}`}>
            View Order
            <ArrowUpRightIcon />
          </Link>
        </div>
      </div>
    </article>
  );
}

export default function MyOrders({ state }: { state: MyOrdersState }) {
  if (state.kind === 'error') {
    return (
      <div className={styles.page}>
        <Intro />
        <section className={`${homeStyles.container} ${styles.listing}`}>
          <div className={styles.empty} role="alert">
            <span className={styles.emptyIcon}>
              <PackageIcon />
            </span>
            <p className={styles.emptyTitle}>We couldn&apos;t load your orders</p>
            <p>Something went wrong reaching CliQ. Please try again in a moment.</p>
            <Link href="?" className={styles.outlineButton}>
              Try again
            </Link>
          </div>
        </section>
      </div>
    );
  }

  const { orders, totalOrders, matchingOrders, counts, status, query, page, totalPages } = state;

  return (
    <div className={styles.page}>
      <Intro />

      <section className={`${homeStyles.container} ${styles.listing}`} aria-label="Your orders">
        {totalOrders === 0 ? (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>
              <PackageIcon />
            </span>
            <p className={styles.emptyTitle}>You haven&apos;t placed any orders yet</p>
            <p>When you place an order, it will appear here so you can track it.</p>
            <Link href="/products" className={styles.solidButton}>
              Start Shopping
            </Link>
          </div>
        ) : (
          <>
            <div className={styles.toolbar}>
              <nav className={styles.tabs} aria-label="Filter orders by status">
                {TABS.map(tab => {
                  const active = status === tab.value;
                  const count = counts[tab.value] ?? 0;
                  if (!active && tab.value !== 'all' && count === 0) return null;
                  return (
                    <Link
                      key={tab.value}
                      href={listingHref(tab.value, query)}
                      scroll={false}
                      aria-current={active ? 'page' : undefined}
                      className={`${styles.tab} ${active ? styles.tabActive : ''}`}>
                      {tab.label}
                      <span className={styles.tabCount}>{count}</span>
                    </Link>
                  );
                })}
              </nav>

              <form className={styles.search} role="search">
                {status !== 'all' && <input type="hidden" name="status" value={status} />}
                <label htmlFor="order-search" className={styles.visuallyHidden}>
                  Search by order number
                </label>
                <SearchIcon />
                <input
                  id="order-search"
                  name="q"
                  type="search"
                  defaultValue={query}
                  placeholder="Search order number"
                  autoComplete="off"
                />
              </form>
            </div>

            {orders.length === 0 ? (
              <div className={styles.empty}>
                <p className={styles.emptyTitle}>
                  {query ? `No orders match “${query}”` : 'No orders with this status'}
                </p>
                <Link href={listingHref('all', '')} className={styles.outlineButton}>
                  Show all orders
                </Link>
              </div>
            ) : (
              <div className={styles.list}>
                {orders.map(order => (
                  <OrderCard key={order.id} order={order} />
                ))}
              </div>
            )}

            {totalPages > 1 && (
              <nav className={styles.pagination} aria-label="Order pages">
                <p className={styles.pageCount}>
                  Page {page} of {totalPages} · {matchingOrders} orders
                </p>
                <div className={styles.pageLinks}>
                  {page > 1 ? (
                    <Link href={listingHref(status, query, page - 1)} className={styles.outlineButton}>
                      Previous
                    </Link>
                  ) : null}
                  {page < totalPages ? (
                    <Link href={listingHref(status, query, page + 1)} className={styles.outlineButton}>
                      Next
                    </Link>
                  ) : null}
                </div>
              </nav>
            )}
          </>
        )}
      </section>
    </div>
  );
}
