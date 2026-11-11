import { useEffect, useState } from "react";
import type { Dispatch, FormEvent, SetStateAction } from "react";
import { Link, useNavigate } from "react-router-dom";
import { downloadShippingLabels, listOrders } from "../../api/orders";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import Badge from "../../components/common/Badge";
import DataTable from "../../components/common/DataTable";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Pagination from "../../components/common/Pagination";
import { useAdminRefresh } from "../../hooks/AdminRefreshContext";
import { useApi } from "../../hooks/useApi";
import { useUrlFilters } from "../../hooks/useUrlFilters";
import type { OrderSummary, PaymentStatus } from "../../types/order";
import { ORDER_STATUSES, PAYMENT_METHODS, PAYMENT_STATUSES, SHIPPING_LABEL_STATUSES } from "../../types/order";
import { formatDate, formatMoney, label } from "../../utils/formatters";

const FILTERS = ["search", "status", "payment_status", "payment_method", "start_date", "end_date"] as const;
type SelectedOrders = Record<string, OrderSummary>;
type PaymentOptionsResult = { key: string; statuses: PaymentStatus[] | null; error: boolean };
const canPrintLabel = (order: OrderSummary) => SHIPPING_LABEL_STATUSES.includes(order.status);

function paymentMethodLabel(method: string) {
  if (method === "CASH_ON_DELIVERY") return "COD";
  if (method === "UPI") return "UPI";
  return label(method);
}

function validDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(value);
  return !Number.isNaN(date.getTime()) && date.toISOString().slice(0, 10) === value;
}

// The backend has no status/payment compatibility map. Its paginated totals
// tell us which payment states actually occur across all matching orders.
function usePaymentOptions(status: string, search: string, method: string, startDate: string, endDate: string, dateError: string | null) {
  const refresh = useAdminRefresh();
  const begin = refresh?.begin;
  const end = refresh?.end;
  const key = JSON.stringify([status, search, method, startDate, endDate, refresh?.version ?? 0]);
  const [loaded, setLoaded] = useState<PaymentOptionsResult>({ key: "", statuses: null, error: false });
  const [cache, setCache] = useState<Record<string, PaymentStatus[]>>({});
  const cached = cache[key];

  useEffect(() => {
    if (!status || dateError || cached) return;
    let cancelled = false;
    begin?.();
    void Promise.allSettled(PAYMENT_STATUSES.map(async (paymentStatus) => {
      const response = await listOrders({ status, search, payment_method: method, start_date: startDate, end_date: endDate, payment_status: paymentStatus, page: 1, page_size: 1 });
      if (!response.meta) throw new Error("Order count unavailable");
      return { paymentStatus, count: response.meta.total_items };
    })).then((results) => {
      if (cancelled) return;
      if (results.some((result) => result.status === "rejected")) {
        setLoaded({ key, statuses: null, error: true });
      } else {
        const statuses = results.flatMap((result) => result.status === "fulfilled" && result.value.count > 0 ? [result.value.paymentStatus] : []);
        setCache((current) => ({ ...current, [key]: statuses }));
        setLoaded({ key, statuses, error: false });
      }
    }).finally(() => end?.());
    return () => { cancelled = true; };
  }, [status, search, method, startDate, endDate, dateError, key, cached, begin, end]);

  return {
    loading: !!status && !dateError && !cached && loaded.key !== key,
    statuses: cached ?? (loaded.key === key ? loaded.statuses : null),
    error: loaded.key === key && loaded.error,
  };
}

// Orders list. Filters live in the URL so a filtered view can be bookmarked/shared.
function OrderSection() {
  const { params, setParams, setFilter: setUrlFilter, setPage } = useUrlFilters();
  const [search, setSearch] = useState(params.get("search") ?? "");
  const [mobileFiltersOpen, setMobileFiltersOpen] = useState(false);
  const query = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? undefined]));
  const page = Number(params.get("page") ?? 1);
  const startDate = params.get("start_date") ?? "";
  const endDate = params.get("end_date") ?? "";
  const orderStatus = params.get("status") ?? "";
  const paymentStatus = params.get("payment_status") ?? "";
  const dateError = (startDate && !validDate(startDate)) || (endDate && !validDate(endDate))
    ? "Enter valid dates."
    : startDate && endDate && endDate < startDate
      ? "The end date cannot be before the start date."
      : null;
  const [selected, setSelected] = useState<SelectedOrders>({});
  const selectedRows = Object.values(selected);
  const eligibleSelected = selectedRows.filter(canPrintLabel);
  const ineligible = selectedRows.filter((order) => !canPrintLabel(order));
  const tooMany = eligibleSelected.length > 100;
  const action = useAction();
  const paymentOptions = usePaymentOptions(orderStatus, params.get("search") ?? "", params.get("payment_method") ?? "", startDate, endDate, dateError);
  const availablePayments = !orderStatus || paymentOptions.error ? PAYMENT_STATUSES : paymentOptions.statuses ?? PAYMENT_STATUSES;
  const invalidPayment = !!orderStatus && !!paymentStatus && !!paymentOptions.statuses && !paymentOptions.statuses.includes(paymentStatus as PaymentStatus);

  useEffect(() => {
    if (!invalidPayment) return;
    setParams((current) => {
      if (current.get("status") !== orderStatus || current.get("payment_status") !== paymentStatus) return current;
      const next = new URLSearchParams(current);
      next.delete("payment_status");
      next.delete("page");
      return next;
    });
  }, [invalidPayment, orderStatus, paymentStatus, setParams]);

  const setFilter = (key: string, value: string) => {
    if ((params.get(key) ?? "") === value) return;
    setSelected({});
    action.setStatus(null);
    setUrlFilter(key, value);
  };
  const submitSearch = (e: FormEvent) => {
    e.preventDefault();
    setFilter("search", search.trim());
  };
  const clearFilters = () => {
    setSearch("");
    setSelected({});
    action.setStatus(null);
    setParams(new URLSearchParams());
  };

  return (
    <div className="record-page orders-page">
      <PageHeader
        title="Orders"
        subtitle="Manage order fulfilment and shipping labels"
        actions={
          <>
            {selectedRows.length > 0 && <button onClick={() => setSelected({})}>Clear selection</button>}
            <button
              className="primary"
              disabled={eligibleSelected.length === 0 || tooMany || action.busy}
              onClick={() => action.run(() => downloadShippingLabels(eligibleSelected.map((order) => order.id)), null, "Could not print labels")}
            >
              Print {eligibleSelected.length || ""} shipping label{eligibleSelected.length === 1 ? "" : "s"}
            </button>
          </>
        }
      />
      <StatusMessage status={action.status} />
      {ineligible.length > 0 && <div className="status status-error label-selection-warning" role="alert">
        {ineligible.length} selected order{ineligible.length === 1 ? " is" : "s are"} no longer eligible for shipping labels. {eligibleSelected.length > 0 && "Eligible orders can still be printed. "}
        <button type="button" onClick={() => setSelected((current) => {
          const next = { ...current };
          ineligible.forEach((order) => { delete next[order.id]; });
          return next;
        })}>Clear invalid selections</button>
      </div>}
      {tooMany && <div className="status status-error" role="alert">Select no more than 100 orders for one label PDF.</div>}
      <p className="muted">Select confirmed, processing, packed, shipped or out-for-delivery orders for shipping labels (up to 100).</p>
      <form className="filters record-responsive-filters" onSubmit={submitSearch}>
        <div className="record-search-row"><GuidedControl className="guided-control--wide" hint="Search by order number, customer name, phone, email, product or SKU." dismissible><input type="search" placeholder="Search orders…" value={search} onChange={(e) => setSearch(e.target.value)} aria-label="Search orders" maxLength={100} /></GuidedControl>
          <button type="submit">Search</button></div>
        <button type="button" className="record-filter-toggle" aria-expanded={mobileFiltersOpen} aria-controls="order-secondary-filters" onClick={() => setMobileFiltersOpen((open) => !open)}>Filters{["status", "payment_status", "payment_method", "start_date", "end_date"].filter((key) => params.has(key)).length ? ` (${["status", "payment_status", "payment_method", "start_date", "end_date"].filter((key) => params.has(key)).length} active)` : ""} {mobileFiltersOpen ? "▴" : "▾"}</button>
        <div id="order-secondary-filters" className="record-secondary-filters" data-open={mobileFiltersOpen}>
        <GuidedControl hint="Filter by the order's current fulfilment status."><select aria-label="Order status" value={orderStatus} onChange={(e) => setFilter("status", e.target.value)}>
          <option value="">All statuses</option>
          {ORDER_STATUSES.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select></GuidedControl>
        <GuidedControl hint="Filter by the payment record's status."><select aria-label="Payment status" value={paymentStatus} disabled={paymentOptions.loading} aria-busy={paymentOptions.loading} onChange={(e) => setFilter("payment_status", e.target.value)}>
          <option value="">All payments</option>
          {availablePayments.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select></GuidedControl>
        <GuidedControl className="guided-control--payment-method" hint="Filter by the method chosen for payment."><select className="order-payment-method-filter" aria-label="Payment method" value={params.get("payment_method") ?? ""} onChange={(e) => setFilter("payment_method", e.target.value)}>
          <option value="">All payment methods</option>
          {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{paymentMethodLabel(m)}</option>)}
        </select></GuidedControl>
        <div className="order-date-range" role="group" aria-label="Order date range">
          <GuidedControl className="guided-control--date" hint="Start of the order date range."><input type="date" aria-label="From date" value={startDate} onChange={(e) => setFilter("start_date", e.target.value)} /></GuidedControl>
          <span className="order-date-range-separator" aria-hidden="true">to</span>
          <GuidedControl className="guided-control--date" hint="End of the order date range."><input type="date" aria-label="To date" value={endDate} min={startDate || undefined} onChange={(e) => setFilter("end_date", e.target.value)} /></GuidedControl>
        </div>
        {FILTERS.some((key) => params.has(key)) && <button type="button" onClick={clearFilters}>Clear filters</button>}
        </div>
      </form>
      {paymentOptions.error && orderStatus && <p className="muted">Available payment statuses could not be checked. All payment options are shown.</p>}
      {dateError ? <div className="status status-error" role="alert">{dateError}</div> : paymentOptions.loading || invalidPayment ? <div className="panel record-table-panel"><div className="state">Checking payment statuses…</div></div> : <OrderResults
        query={{ ...query, page }}
        queryKey={params.toString()}
        selected={selected}
        setSelected={setSelected}
        onPageChange={setPage}
      />}
    </div>
  );
}

function OrderResults({ query, queryKey, selected, setSelected, onPageChange }: {
  query: object;
  queryKey: string;
  selected: SelectedOrders;
  setSelected: Dispatch<SetStateAction<SelectedOrders>>;
  onPageChange: (page: number) => void;
}) {
  const navigate = useNavigate();
  const { data, meta, loading, error, reload } = useApi(() => listOrders(query), [queryKey]);
  const rows = loading ? null : data;
  const eligiblePageRows = (rows ?? []).filter(canPrintLabel);
  const pageIds = eligiblePageRows.map((order) => order.id);
  const allOnPage = pageIds.length > 0 && pageIds.every((id) => id in selected);
  const [selectionNotice, setSelectionNotice] = useState<{ key: string; message: string } | null>(null);

  useEffect(() => {
    if (!rows) return;
    setSelected((current) => {
      let next = current;
      for (const order of rows) {
        if (current[order.id] && current[order.id] !== order) {
          if (next === current) next = { ...current };
          next[order.id] = order;
        }
      }
      return next;
    });
  }, [rows, setSelected]);

  const toggle = (order: OrderSummary) => {
    if (!canPrintLabel(order)) return;
    setSelected((current) => {
      const next = { ...current };
      if (order.id in next) delete next[order.id];
      else next[order.id] = order;
      return next;
    });
  };

  return (
      <div className="panel record-table-panel">
        {!loading && !error && rows && <GuidedControl className="guided-control--wide" hint="Select eligible orders to print shipping labels together."><label className="check">
          <input
            type="checkbox"
            aria-label="Select all eligible on this page"
            checked={allOnPage}
            onChange={() => {
              if (eligiblePageRows.length === 0) {
                setSelectionNotice({ key: queryKey, message: "No orders on this page are eligible for shipping labels. Eligible statuses: Confirmed, Processing, Packed, Shipped, and Out for Delivery." });
                return;
              }
              setSelectionNotice(null);
              setSelected((current) => {
                const next = { ...current };
                if (allOnPage) pageIds.forEach((id) => { delete next[id]; });
                else eligiblePageRows.forEach((order) => { next[order.id] = order; });
                return next;
              });
            }}
          />
          Select all eligible on this page <span className="muted">({eligiblePageRows.length} eligible)</span>
        </label></GuidedControl>}
        {selectionNotice?.key === queryKey && <p className="muted label-selection-notice" role="status">{selectionNotice.message}</p>}
        <DataTable
          rows={rows}
          loading={loading}
          error={loading ? null : error}
          onRetry={reload}
          empty="No orders match these filters."
          rowKey={(o) => o.id}
          onRowClick={(o) => navigate(`/orders/${o.id}`)}
          columns={[
            {
              key: "select",
              header: "",
              render: (o) => (
                <input type="checkbox" aria-label={`Select ${o.order_number}`} title={canPrintLabel(o) ? undefined : "Shipping labels are unavailable for this order status"} disabled={!canPrintLabel(o)} checked={o.id in selected} onClick={(e) => e.stopPropagation()} onChange={() => toggle(o)} />
              ),
            },
            { key: "order_number", header: "Order", render: (o) => <Link to={`/orders/${o.id}`} title="Open order and customer details" onClick={(e) => e.stopPropagation()}>{o.order_number}</Link> },
            { key: "created_at", header: "Placed", render: (o) => formatDate(o.created_at) },
            { key: "status", header: "Status", render: (o) => <Badge value={o.status} /> },
            { key: "payment_method", header: "Method", render: (o) => paymentMethodLabel(o.payment_method) },
            { key: "payment_status", header: "Payment", render: (o) => <Badge value={o.payment_status} /> },
            { key: "tracking_number", header: "Tracking" },
            { key: "total_amount", header: "Total", align: "right", render: (o) => formatMoney(o.total_amount, o.currency) },
            { key: "actions", header: "Actions", render: (o) => <Link className="order-row-action" to={`/orders/${o.id}`} onClick={(e) => e.stopPropagation()}>View</Link> },
          ]}
        />
        <Pagination meta={loading ? null : meta} onPageChange={onPageChange} />
      </div>
  );
}

export default OrderSection;
