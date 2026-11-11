import Image from 'next/image';
import Link from 'next/link';
import type { ReactNode } from 'react';

import homeStyles from '@/app/(storefront)/(home)/home/_components/luxe/Home.module.css';
import { signInUrl } from '@/lib/auth/sign-in-url';
import { formatDate, formatMoney } from '@/lib/format';
import { orderStatusMeta } from '@/lib/orders/status';
import type { OrderSummary } from '@/types/orders';

import { HELP_TOPICS, type HelpTopic, type HelpTopicIcon, SUPPORT_EMAIL } from './helpTopics';
import styles from './HelpCenter.module.css';

export type HelpView = 'orders' | 'topics' | 'write';

export interface HelpOrder extends OrderSummary {
  /** The first line's product and variant, or null when the order's detail could not be read. */
  first_item: { product_name: string; variant_name: string } | null;
  item_count: number | null;
  preview_image: string | null;
}

export type HelpOrdersState =
  | { kind: 'signed-out' }
  | { kind: 'error' }
  | { kind: 'ready'; orders: HelpOrder[] };

export interface HelpCenterProps {
  view: HelpView;
  /** Set only when a topic is open, which is a state of the `topics` view. */
  topic: HelpTopic | null;
  /** Index of the question to open on arrival, from a quick link. */
  openQuestion: number | null;
  /** Read only for the `orders` view. */
  orders: HelpOrdersState | null;
}

const TONE_DOT: Record<string, string> = {
  amber: styles.dotAmber,
  blue: styles.dotBlue,
  green: styles.dotGreen,
  red: styles.dotRed,
  neutral: styles.dotNeutral,
};

const ICON_TINT: Record<HelpTopicIcon, string> = {
  account: styles.tintRose,
  returns: styles.tintStone,
  shipping: styles.tintChampagne,
  offers: styles.tintSand,
  payments: styles.tintSage,
  cancel: styles.tintClay,
};

const MAILTO = `mailto:${SUPPORT_EMAIL}`;

/* --------------------------------- Icons --------------------------------- */

function Svg({ size = 20, strokeWidth = 1.4, children }: { size?: number; strokeWidth?: number; children: ReactNode }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <Svg size={16} strokeWidth={1.6}>
      <path d="m9 6 6 6-6 6" />
    </Svg>
  );
}

function ChevronDownIcon() {
  return (
    <Svg size={16} strokeWidth={1.6}>
      <path d="m6 9 6 6 6-6" />
    </Svg>
  );
}

function BagIcon() {
  return (
    <Svg size={28} strokeWidth={1.2}>
      <path d="M6 8h12l-1 12H7L6 8Z" />
      <path d="M9 8V6a3 3 0 0 1 6 0v2" />
    </Svg>
  );
}

function MailIcon() {
  return (
    <Svg size={18}>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </Svg>
  );
}

function TopicIcon({ icon, size = 20 }: { icon: HelpTopicIcon; size?: number }) {
  switch (icon) {
    case 'account':
      return (
        <Svg size={size}>
          <circle cx="9" cy="8" r="3.5" />
          <path d="M2.5 20a6.5 6.5 0 0 1 13 0" />
          <path d="M15.5 4.6a3.5 3.5 0 0 1 0 6.8M18 14.2a6.5 6.5 0 0 1 3.5 5.8" />
        </Svg>
      );
    case 'returns':
      return (
        <Svg size={size}>
          <circle cx="12" cy="12" r="9" />
          <path d="M9 10h6a2 2 0 0 1 0 4h-5" />
          <path d="m11 8-2 2 2 2" />
        </Svg>
      );
    case 'shipping':
      return (
        <Svg size={size}>
          <path d="M2.5 6h11v10h-11z" />
          <path d="M13.5 9.5h4l3 3.5V16h-7" />
          <circle cx="6.5" cy="17.5" r="1.8" />
          <circle cx="17" cy="17.5" r="1.8" />
        </Svg>
      );
    case 'offers':
      return (
        <Svg size={size}>
          <path d="m12 2.5 2.2 1.6 2.7-.1.9 2.6 2.2 1.6-.8 2.6.8 2.6-2.2 1.6-.9 2.6-2.7-.1L12 21.5l-2.2-1.6-2.7.1-.9-2.6L4 15.8l.8-2.6L4 10.6l2.2-1.6.9-2.6 2.7.1L12 2.5Z" />
          <path d="m9.5 14.5 5-5" />
          <circle cx="9.7" cy="9.7" r=".6" />
          <circle cx="14.3" cy="14.3" r=".6" />
        </Svg>
      );
    case 'payments':
      return (
        <Svg size={size}>
          <rect x="2.5" y="6" width="19" height="13" rx="2" />
          <path d="M2.5 10h19" />
          <path d="M6 15h4" />
        </Svg>
      );
    case 'cancel':
      return (
        <Svg size={size}>
          <path d="M5 8h14l-1 12H6L5 8Z" />
          <path d="M9 8V6a3 3 0 0 1 6 0v2" />
          <path d="m10 12 4 4M14 12l-4 4" />
        </Svg>
      );
  }
}

/* --------------------------------- Pieces -------------------------------- */

function TopicBadge({ icon, size = 'md' }: { icon: HelpTopicIcon; size?: 'md' | 'lg' }) {
  return (
    <span className={`${styles.topicBadge} ${size === 'lg' ? styles.topicBadgeLg : ''} ${ICON_TINT[icon]}`}>
      <TopicIcon icon={icon} />
    </span>
  );
}

function Intro() {
  return (
    <section className={`${homeStyles.container} ${styles.intro}`}>
      <div className={styles.introText}>
        <nav className={styles.crumb} aria-label="Breadcrumb">
          <Link href="/">Home</Link>
          <span aria-hidden="true">/</span>
          <span aria-current="page">Contact</span>
        </nav>
        <h1 className={styles.title}>Help Centre</h1>
        <p className={styles.description}>We are here to help you.</p>
      </div>

      <div className={styles.manageCard}>
        <span className={styles.manageIcon}>
          <BagIcon />
        </span>
        <div className={styles.manageText}>
          <p className={styles.manageTitle}>Track, cancel, return/exchange</p>
          <p className={styles.manageMeta}>Manage your purchases</p>
        </div>
        <Link href="/account/orders" className={styles.outlineButton}>
          Orders
        </Link>
      </div>
    </section>
  );
}

function QueryMenu({ view }: { view: HelpView }) {
  const items: { view: HelpView; label: string; href: string }[] = [
    { view: 'orders', label: 'Order Related Queries', href: '?view=orders' },
    { view: 'topics', label: 'Non-order Related Issues', href: '?view=topics' },
  ];

  return (
    <aside className={styles.aside}>
      <nav aria-label="Select query type">
        <p className={styles.asideLabel}>Select query type</p>
        <ul className={styles.menu}>
          {items.map(item => (
            <li key={item.view}>
              <Link
                href={item.href}
                scroll={false}
                aria-current={view === item.view ? 'page' : undefined}
                className={`${styles.menuLink} ${view === item.view ? styles.menuLinkActive : ''}`}>
                {item.label}
                <ChevronRightIcon />
              </Link>
            </li>
          ))}
        </ul>
        <hr className={styles.menuRule} />
        <ul className={styles.menu}>
          <li>
            <Link href="/faq" className={styles.menuLink}>
              Frequently Asked Questions
              <ChevronRightIcon />
            </Link>
          </li>
        </ul>
      </nav>

      <p className={styles.asideNote}>
        Prefer to write?{' '}
        <Link
          href="?view=write"
          scroll={false}
          aria-current={view === 'write' ? 'page' : undefined}
          className={styles.asideNoteLink}>
          Write to the CliQ studio
        </Link>
      </p>
    </aside>
  );
}

function WriteToUs() {
  return (
    <div className={styles.writeRow}>
      <a href={MAILTO} className={styles.solidButton}>
        <MailIcon />
        Write to us
      </a>
      <p className={styles.writeMeta}>Average response time: within one business day</p>
    </div>
  );
}

/* ------------------------------ Orders panel ----------------------------- */

function OrderRow({ order }: { order: HelpOrder }) {
  const meta = orderStatusMeta(order.status);
  const href = `/account/orders/${encodeURIComponent(order.order_number)}`;

  return (
    <li className={styles.orderCard}>
      <p className={styles.orderStatus}>
        <span className={`${styles.dot} ${TONE_DOT[meta.tone]}`} aria-hidden="true" />
        <span className={styles.orderStatusLabel}>{meta.label}</span>
        <span className={styles.orderStatusMeta}>
          Order #{order.order_number} · {formatDate(order.created_at)}
        </span>
      </p>

      <Link href={href} className={styles.orderItem} aria-label={`Get help with order #${order.order_number}`}>
        <span className={styles.orderThumb}>
          {order.preview_image ? (
            <Image src={order.preview_image} alt="" fill sizes="64px" className={styles.orderThumbImg} />
          ) : (
            <BagIcon />
          )}
        </span>
        <span className={styles.orderItemText}>
          <span className={styles.orderItemName}>{order.first_item?.product_name ?? `Order #${order.order_number}`}</span>
          <span className={styles.orderItemMeta}>
            {order.first_item ? order.first_item.variant_name : null}
            {order.first_item && order.item_count !== null && ' · '}
            {order.item_count !== null && `${order.item_count} ${order.item_count === 1 ? 'item' : 'items'}`}
          </span>
          <span className={styles.orderItemAmount}>{formatMoney(order.total_amount, order.currency)}</span>
        </span>
        <span className={styles.orderChevron}>
          <ChevronRightIcon />
        </span>
      </Link>
    </li>
  );
}

function OrdersPanel({ state }: { state: HelpOrdersState }) {
  if (state.kind === 'signed-out') {
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>
          <BagIcon />
        </span>
        <p className={styles.emptyTitle}>Sign in to get help with an order</p>
        <p>Your recent orders appear here so you can pick the one you need help with.</p>
        <div className={styles.emptyActions}>
          <Link href={signInUrl('/contact?view=orders')} className={styles.solidButton}>
            Sign In
          </Link>
          <Link href="?view=topics" scroll={false} className={styles.outlineButton}>
            Browse Topics
          </Link>
        </div>
      </div>
    );
  }

  if (state.kind === 'error') {
    return (
      <div className={styles.empty} role="alert">
        <p className={styles.emptyTitle}>We couldn&apos;t load your orders</p>
        <p>Something went wrong reaching CliQ. Try again in a moment, or write to the studio with your order number.</p>
        <div className={styles.emptyActions}>
          <Link href="?view=orders" className={styles.outlineButton}>
            Try again
          </Link>
        </div>
      </div>
    );
  }

  if (state.orders.length === 0) {
    return (
      <div className={styles.empty}>
        <span className={styles.emptyIcon}>
          <BagIcon />
        </span>
        <p className={styles.emptyTitle}>You haven&apos;t placed any orders yet</p>
        <p>For anything else, browse the topics or write to the studio.</p>
        <div className={styles.emptyActions}>
          <Link href="/products" className={styles.solidButton}>
            Start Shopping
          </Link>
          <Link href="?view=topics" scroll={false} className={styles.outlineButton}>
            Browse Topics
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.ordersPanel}>
      <p className={styles.panelLabel}>Select the order we can help you with</p>
      <ul className={styles.orderList}>
        {state.orders.map(order => (
          <OrderRow key={order.id} order={order} />
        ))}
      </ul>
      <Link href="/account/orders" className={styles.textLink}>
        View all orders
        <ChevronRightIcon />
      </Link>
    </div>
  );
}

/* ------------------------------ Topics panel ----------------------------- */

function TopicsPanel() {
  const featured = HELP_TOPICS[0];

  return (
    <div>
      <h2 className={styles.panelTitle}>Browse Topics</h2>
      <ul className={styles.topicGrid}>
        {HELP_TOPICS.map(topic => (
          <li key={topic.slug}>
            <Link href={`?view=topics&topic=${topic.slug}`} scroll={false} className={styles.topicCard}>
              <TopicBadge icon={topic.icon} />
              <span className={styles.topicCardTitle}>{topic.title}</span>
            </Link>
          </li>
        ))}
      </ul>

      <ul className={styles.quickList} aria-label={`Popular ${featured.title.toLowerCase()} questions`}>
        {featured.questions.map((question, index) => (
          <li key={question.q}>
            <Link href={`?view=topics&topic=${featured.slug}&q=${index}`} scroll={false} className={styles.quickLink}>
              {question.q}
              <ChevronRightIcon />
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}

function TopicDetail({ topic, openIndex }: { topic: HelpTopic; openIndex: number | null }) {
  return (
    <div>
      <nav className={styles.topicTabs} aria-label="Help topics">
        {HELP_TOPICS.map(item => {
          const active = item.slug === topic.slug;
          return (
            <Link
              key={item.slug}
              href={`?view=topics&topic=${item.slug}`}
              scroll={false}
              aria-current={active ? 'page' : undefined}
              className={`${styles.topicTab} ${active ? styles.topicTabActive : ''}`}>
              <TopicBadge icon={item.icon} size="lg" />
              <span>{item.title}</span>
            </Link>
          );
        })}
      </nav>

      <section className={styles.topicCardDetail} aria-labelledby="help-topic-title">
        <header className={styles.topicHeader}>
          <TopicIcon icon={topic.icon} size={22} />
          <h2 id="help-topic-title" className={styles.topicTitle}>
            {topic.title}
          </h2>
        </header>
        <p className={styles.topicSummary}>{topic.summary}</p>
        {topic.link && (
          <Link href={topic.link.href} className={styles.textLink}>
            {topic.link.label}
            <ChevronRightIcon />
          </Link>
        )}

        <div className={styles.accordion}>
          {topic.questions.map((question, index) => (
            <details key={question.q} className={styles.question} open={index === openIndex}>
              <summary className={styles.questionSummary}>
                {question.q}
                <span className={styles.questionChevron}>
                  <ChevronDownIcon />
                </span>
              </summary>
              <div className={styles.answer}>
                {question.a.map(paragraph => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
                <WriteToUs />
              </div>
            </details>
          ))}
        </div>
      </section>
    </div>
  );
}

/* ------------------------------- Write panel ----------------------------- */

function WritePanel() {
  return (
    <div>
      <h2 className={styles.panelTitle}>Write to the CliQ studio</h2>
      <p className={styles.topicSummary}>
        For help with an order, sizing, returns or anything else, reach out and a member of the team will get back to
        you within one business day. Include your order number if your question is about an order.
      </p>
      <div className={styles.contactGrid}>
        <div className={styles.contactCard}>
          <p className={styles.contactLabel}>Email</p>
          <p className={styles.contactValue}>
            <a href={MAILTO}>{SUPPORT_EMAIL}</a>
          </p>
        </div>
        <div className={styles.contactCard}>
          <p className={styles.contactLabel}>Orders &amp; Returns</p>
          <p className={styles.contactValue}>
            <a href={`${MAILTO}?subject=${encodeURIComponent('Order help')}`}>{SUPPORT_EMAIL}</a>
          </p>
        </div>
        <div className={styles.contactCard}>
          <p className={styles.contactLabel}>Hours</p>
          <p className={styles.contactValue}>Mon&ndash;Sat, 10am&ndash;7pm IST</p>
        </div>
      </div>
    </div>
  );
}

/**
 * The help centre: a query-type menu beside a panel that changes with it.
 * Every state is a URL on /contact (`?view=`, `?topic=`, `?q=`), so it
 * renders on the server, works without JavaScript and can be linked to.
 */
export default function HelpCenter({ view, topic, openQuestion, orders }: HelpCenterProps) {
  return (
    <div className={styles.page}>
      <Intro />
      <div className={`${homeStyles.container} ${styles.layout}`}>
        <QueryMenu view={view} />
        <div className={styles.panel}>
          {view === 'orders' && orders && <OrdersPanel state={orders} />}
          {view === 'topics' && (topic ? <TopicDetail topic={topic} openIndex={openQuestion} /> : <TopicsPanel />)}
          {view === 'write' && <WritePanel />}
        </div>
      </div>
    </div>
  );
}
