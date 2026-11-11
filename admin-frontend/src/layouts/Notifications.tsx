import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboardOverview } from "../api/dashboard";
import { useAuth } from "../auth/AuthContext";
import { P } from "../auth/permissions";
import { useApi } from "../hooks/useApi";
import type { DashboardOverview } from "../types/dashboard";
import { formatDate, formatMoney, label } from "../utils/formatters";

type Category = "Orders" | "Sales" | "Alerts";
type Tab = "All" | Category;
interface Notice { id: string; category: Category; title: string; detail: string; to: string; timestamp: string; observed?: boolean }
interface Saved { read: string[]; observed: Record<string, string> }
const tabs: Tab[] = ["All", "Orders", "Sales", "Alerts"];

function loadSaved(key: string): Saved {
  try {
    const value = JSON.parse(localStorage.getItem(key) ?? "null");
    return { read: Array.isArray(value?.read) ? value.read.filter((id: unknown) => typeof id === "string") : [], observed: value?.observed && typeof value.observed === "object" ? value.observed : {} };
  } catch { return { read: [], observed: {} }; }
}
function save(key: string, value: Saved) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Read states still work in memory when storage is unavailable. */ }
}

function noticesFrom(data: DashboardOverview, allowed: (permission: string) => boolean, observed: Record<string, string>): Notice[] {
  const notices: Notice[] = [];
  for (const order of data.recent_orders) {
    if (allowed(P.ordersView)) notices.push({ id: `order:${order.order_id}:${order.order_status}`, category: "Orders", title: `Order ${order.order_number}`, detail: `${label(order.order_status)} · ${formatMoney(order.total_amount, order.currency)}`, to: `/orders/${order.order_id}`, timestamp: order.created_at });
    if (order.payment_status === "PAID" && allowed(P.ordersView) && allowed(P.paymentsView)) notices.push({ id: `sale:${order.order_id}`, category: "Sales", title: `Sale · ${order.order_number}`, detail: `Payment received · ${formatMoney(order.total_amount, order.currency)}`, to: `/orders/${order.order_id}`, timestamp: order.created_at });
  }
  if (allowed(P.catalogueView)) {
    for (const [items, status] of [[data.inventory.out_of_stock_variants, "Out of stock"], [data.inventory.low_stock_variants, "Low stock"]] as const) {
      for (const item of items) {
        const id = `stock:${item.variant_id ?? item.sku}:${status}:${item.available_quantity}`;
        observed[id] ??= new Date().toISOString();
        notices.push({ id, category: "Alerts", title: `${status} · ${item.product_name}`, detail: `${item.sku} · ${item.available_quantity} available`, to: `/products/${item.product_id}`, timestamp: observed[id], observed: true });
      }
    }
  }
  return notices.sort((a, b) => Date.parse(b.timestamp) - Date.parse(a.timestamp));
}

export default function Notifications() {
  const { user } = useAuth();
  return <NotificationBell key={`${user?.tenant_id}:${user?.id}`} storageKey={`cliq:notifications:${user?.tenant_id}:${user?.id}`} />;
}

function NotificationBell({ storageKey }: { storageKey: string }) {
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(() => loadSaved(storageKey));
  const [unread, setUnread] = useState(0);
  const trigger = useRef<HTMLButtonElement>(null);
  const { can, isAdmin } = useAuth();
  const close = useCallback(() => { setOpen(false); trigger.current?.focus(); }, []);
  const markRead = (ids: string[]) => {
    setSaved((current) => {
      const next = { ...current, read: [...new Set([...current.read, ...ids])].slice(-1000) };
      save(storageKey, { ...loadSaved(storageKey), read: next.read });
      return next;
    });
  };
  return <div className="header-notification-anchor">
    <button type="button" ref={trigger} className="header-notifications" aria-label={unread ? `Notifications, ${unread} unread` : "Notifications"} title="Notifications" aria-haspopup="dialog" aria-expanded={open} onClick={() => open ? close() : setOpen(true)}>
      <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9 M10 21h4 M12 2V1" /></svg>
      {unread > 0 && <span className="notification-bell-dot" aria-hidden="true" />}
    </button>
    {open && <NotificationDialog onClose={close} trigger={trigger}>
      {(titleId) => isAdmin || can(P.dashboard)
        ? <NotificationFeed titleId={titleId} storageKey={storageKey} read={saved.read} markRead={markRead} onUnread={setUnread} onClose={close} />
        : <><NotificationHeading titleId={titleId} onClose={close} /><p className="notification-state">Dashboard access is required to view store alerts.</p></>}
    </NotificationDialog>}
  </div>;
}

function NotificationDialog({ onClose, trigger, children }: { onClose: () => void; trigger: React.RefObject<HTMLButtonElement | null>; children: (titleId: string) => React.ReactNode }) {
  const titleId = useId();
  const dialog = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const position = () => {
      if (!dialog.current || !trigger.current) return;
      const bell = trigger.current.getBoundingClientRect();
      const gap = 16;
      const height = window.innerHeight;
      const desiredHeight = Math.min(height * .78, Math.max(0, height - gap * 2));
      const below = height - bell.bottom - 12 - gap;
      const above = bell.top - 12 - gap;
      const top = below < 240 && above > below
        ? Math.max(gap, bell.top - 12 - desiredHeight)
        : Math.max(gap, Math.min(bell.bottom + 12, height - gap));
      dialog.current.style.top = `${top}px`;
      dialog.current.style.maxHeight = `${Math.max(0, height - top - gap)}px`;
    };
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
  }, [trigger]);
  useEffect(() => {
    dialog.current?.querySelector<HTMLButtonElement>(".notification-close")?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.stopPropagation(); onClose(); }
    };
    const outside = (event: PointerEvent) => {
      if (!dialog.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) onClose();
    };
    const focusOutside = (event: FocusEvent) => {
      if (!dialog.current?.contains(event.target as Node) && !trigger.current?.contains(event.target as Node)) onClose();
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", outside);
    document.addEventListener("focusin", focusOutside);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("focusin", focusOutside);
    };
  }, [onClose, trigger]);
  return <div ref={dialog} className="notification-popover" role="dialog" aria-labelledby={titleId}>
    {children(titleId)}
  </div>;
}

function NotificationHeading({ titleId, onClose, onRefresh, loading = false }: { titleId: string; onClose: () => void; onRefresh?: () => void; loading?: boolean }) {
  return <div className="notification-heading">
    <div><span className="notification-eyebrow">CliQ. WORKSPACE</span><h2 id={titleId}>Notifications</h2></div>
    <div className="notification-heading-actions">
      {onRefresh && <button type="button" className="notification-refresh" aria-label="Refresh notifications" title={loading ? "Refreshing notifications…" : "Refresh notifications"} aria-busy={loading} disabled={loading} onClick={onRefresh}>
        <svg className={loading ? "refresh-spinning" : undefined} aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 7v5h-5 M4 17v-5h5 M6 7a7 7 0 0 1 12-1l2 6 M18 17a7 7 0 0 1-12 1l-2-6" /></svg>
      </button>}
      <button type="button" className="notification-close" aria-label="Close notifications" onClick={onClose}>×</button>
    </div>
  </div>;
}

function NotificationFeed({ titleId, storageKey, read, markRead, onUnread, onClose }: { titleId: string; storageKey: string; read: string[]; markRead: (ids: string[]) => void; onUnread: (count: number) => void; onClose: () => void }) {
  const { can, isAdmin } = useAuth();
  const [tab, setTab] = useState<Tab>("All");
  const tabId = useId();
  const { data, loading, error, reload } = useApi(async () => {
    const response = await getDashboardOverview();
    const saved = loadSaved(storageKey);
    const notices = noticesFrom(response.data, (permission) => isAdmin || can(permission), saved.observed);
    save(storageKey, saved);
    return { ...response, data: notices };
  }, [storageKey]);
  const notices = data ?? [];
  const unread = notices.filter((notice) => !read.includes(notice.id)).length;
  useEffect(() => { if (!loading && !error) onUnread(unread); }, [unread, loading, error, onUnread]);
  const visible = notices.filter((notice) => tab === "All" || notice.category === tab);
  return <>
    <NotificationHeading titleId={titleId} onClose={onClose} onRefresh={reload} loading={loading} />
    <div className="notification-toolbar"><span>{unread} unread</span><button type="button" className="link" disabled={loading || !unread} onClick={() => markRead(notices.map((notice) => notice.id))}>Mark all as read</button></div>
    <div className="notification-tabs" role="tablist" aria-label="Notification categories">
      {tabs.map((category, index) => <button key={category} type="button" role="tab" id={`${tabId}-${category}`} aria-selected={tab === category} aria-controls={`${tabId}-panel`} tabIndex={tab === category ? 0 : -1} onClick={() => setTab(category)} onKeyDown={(event) => {
        const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : event.key === "ArrowLeft" ? (index + tabs.length - 1) % tabs.length : event.key === "Home" ? 0 : event.key === "End" ? tabs.length - 1 : -1;
        if (next < 0) return;
        event.preventDefault(); setTab(tabs[next]); document.getElementById(`${tabId}-${tabs[next]}`)?.focus();
      }}>{category}</button>)}
    </div>
    <div className="notification-scroll" role="tabpanel" id={`${tabId}-panel`} aria-labelledby={`${tabId}-${tab}`} tabIndex={0}>
      {loading && <p className="notification-state" role="status">Loading notifications…</p>}
      {!loading && error && <p className="notification-state" role="alert">Could not load notifications. {error}</p>}
      {!loading && !error && (visible.length ? <ul className="notification-list">{visible.map((notice) => {
        const unread = !read.includes(notice.id);
        return <li key={notice.id}><Link className={unread ? "notification-unread" : ""} to={notice.to} onClick={() => { markRead([notice.id]); onUnread(Math.max(0, notices.filter((item) => !read.includes(item.id)).length - (unread ? 1 : 0))); onClose(); }}>
          <span className={`notification-category notification-category-${notice.category.toLowerCase()}`} aria-hidden="true">{notice.category === "Orders" ? "▤" : notice.category === "Sales" ? "₹" : "!"}</span>
          <span className="notification-copy"><strong>{notice.title}</strong><span>{notice.detail}</span><time dateTime={notice.timestamp}>{notice.observed ? "First observed " : "Order placed "}{formatDate(notice.timestamp)}</time></span>
          {unread && <span className="notification-unread-dot" role="img" aria-label="Unread" />}
        </Link></li>;
      })}</ul> : <p className="notification-state">{tab === "All" ? "You're all caught up. No notifications yet." : `No ${tab.toLowerCase()} notifications yet.`}</p>)}
    </div>
    <div className="notification-footer"><span>Read status saved on this browser</span></div>
  </>;
}
