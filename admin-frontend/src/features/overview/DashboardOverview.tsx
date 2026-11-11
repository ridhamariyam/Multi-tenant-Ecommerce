import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { getDashboardOverview } from "../../api/dashboard";
import { getReport } from "../../api/reports";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ContextualGuidance from "../../components/guidance/ContextualGuidance";
import PageHeader from "../../components/common/PageHeader";
import { useApi } from "../../hooks/useApi";
import type { DashboardOverview as OverviewData } from "../../types/dashboard";
import { formatDate, formatMoney, formatPct } from "../../utils/formatters";
import { inventoryProducts } from "./dashboardData";
import type { InventoryRow, SalesReport } from "./dashboardData";
import DashboardInventory from "./DashboardInventory";
import DashboardTrend from "./DashboardTrend";
import { currentWeekRange, DASHBOARD_PERIODS, dashboardPeriodRange } from "./dashboardPeriod";
import type { DashboardPeriod } from "./dashboardPeriod";
import "./dashboard.css";

type Tab = "overview" | "sales" | "orders" | "inventory";
const TABS: { value: Tab; label: string }[] = [
  { value: "overview", label: "Overview" },
  { value: "sales", label: "Sales Performance" },
  { value: "orders", label: "Order Operations" },
  { value: "inventory", label: "Inventory Health" },
];
interface ProductSale { product_id: string; product_name: string; units_sold: number; net_sales: string }

function PeriodSelect({ value, onChange }: { value: DashboardPeriod; onChange: (value: DashboardPeriod) => void }) {
  return <div className="dashboard-period-control"><label className="dashboard-period">Date range
    <select aria-label="Dashboard date range" value={value} onChange={(event) => onChange(event.target.value as DashboardPeriod)}>
      {DASHBOARD_PERIODS.map((period) => <option key={period.value} value={period.value}>{period.label}</option>)}
    </select>
  </label><ContextualGuidance dismissible>Choose the period for dashboard revenue and sales trends.</ContextualGuidance></div>;
}

function Metric({ label, value, to, hint }: { label: string; value: string | number; to?: string; hint?: string }) {
  const content = <><span className="stat-label">{label}</span><strong className="stat-value">{value}</strong>{hint && <span className="stat-hint">{hint}</span>}</>;
  return to ? <Link className="stat-card dashboard-metric-link" to={to}>{content}</Link> : <div className="stat-card">{content}</div>;
}

function ProductList({ title, rows, loading, error, currency, limit = 3 }: { title: string; rows: ProductSale[] | null; loading: boolean; error: string | null; currency?: string; limit?: number }) {
  const { can } = useAuth();
  return <section className="panel dashboard-products" aria-label={title}>
    <div className="panel-title"><h3>{title}</h3>{can(P.catalogueView) && <Link to="/products">View products</Link>}</div>
    {loading ? <p className="state" role="status">Loading top products…</p>
      : error || !rows ? <p className="state">Product sales are unavailable.</p>
        : rows.length ? <ol>{rows.slice(0, limit).map((product) => <li key={product.product_id}>
          <span>{can(P.catalogueView) ? <Link to={`/products/${product.product_id}`}>{product.product_name}</Link> : product.product_name}<small>{product.units_sold} units sold</small></span>
          <strong>{currency ? formatMoney(product.net_sales, currency) : "Revenue unavailable"}</strong>
        </li>)}</ol> : <p className="muted">No product sales in this period.</p>}
  </section>;
}

function SalesPerformance({ range, report, loading, error, canReport }: { range: ReturnType<typeof dashboardPeriodRange>; report: SalesReport | null; loading: boolean; error: string | null; canReport: boolean }) {
  const previous = useApi(() => canReport
    ? getReport<SalesReport>("sales", { start_date: range.previous_start_date, end_date: range.previous_end_date, group_by: "day" })
    : Promise.reject(new Error("Reports access required")), [range.previous_start_date, range.previous_end_date, canReport]);
  const products = useApi(() => canReport
    ? getReport<ProductSale[]>("sales-by-product", { start_date: range.start_date, end_date: range.end_date })
    : Promise.reject(new Error("Reports access required")), [range.start_date, range.end_date, canReport]);
  const currentRevenue = report ? Number(report.summary.revenue) : null;
  const previousRevenue = previous.data ? Number(previous.data.summary.revenue) : null;
  const comparison = currentRevenue !== null && previousRevenue !== null && previousRevenue > 0
    ? (currentRevenue - previousRevenue) / previousRevenue * 100 : null;
  return <div className="dashboard-sales-performance">
    <div className="dashboard-section-heading"><div><h3>Sales performance</h3><p className="muted">Non-cancelled orders · UTC dates</p></div><Link to="/reports">Detailed reports ↗</Link></div>
    {loading ? <p className="state" role="status">Loading sales performance…</p>
      : error || !report ? <p className="state">Sales performance is unavailable. Report access is required.</p>
        : <>
          <div className="stat-grid dashboard-performance-kpis">
            <Metric label="Average order value" value={formatMoney(report.summary.average_order_value, report.currency)} />
            <Metric label="Booked value vs prior period" value={previous.loading ? "Loading…" : previous.error ? "Unavailable" : comparison === null ? "No comparison" : formatPct(comparison)} hint={previous.data ? `Previous: ${formatMoney(previous.data.summary.revenue, report.currency)}` : undefined} />
          </div>
          <div className="dashboard-performance-charts">
            <section className="panel"><DashboardTrend title="Booked order value trend" rows={report.rows} metric="revenue" currency={report.currency} /></section>
            <section className="panel"><DashboardTrend title="Order trend" rows={report.rows} metric="orders" /></section>
          </div>
        </>}
    <ProductList title="Top products this period" rows={products.data} loading={products.loading} error={products.error} currency={report?.currency} limit={5} />
  </div>;
}

function OrderOperations({ data }: { data: OverviewData }) {
  const { can } = useAuth();
  const attention = data.insights?.attention;
  const stages = [
    { label: "Awaiting confirmation", count: attention?.new_orders, to: "/orders?status=PENDING", detail: "Pending" },
    { label: "Pending packing", count: attention?.awaiting_packing, to: "/orders", detail: "Confirmed + processing" },
    { label: "Pending shipping", count: attention?.awaiting_shipment, to: "/orders?status=PACKED", detail: "Packed" },
  ];
  return <div className="dashboard-order-operations">
    <section className="panel"><div className="panel-title"><h3>Order pipeline</h3>{can(P.ordersView) && <Link to="/orders">View all orders</Link>}</div>
      <div className="stat-grid dashboard-pipeline">{stages.map((stage) => <Metric key={stage.label} label={stage.label} value={stage.count ?? "Unavailable"} to={can(P.ordersView) ? stage.to : undefined} hint={stage.detail} />)}</div>
    </section>
    <section className="panel dashboard-recent-orders"><div className="panel-title"><h3>Recent orders</h3>{can(P.ordersView) && <Link to="/orders">All orders</Link>}</div>
      {data.recent_orders.length ? <ul>{data.recent_orders.slice(0, 5).map((order) => <li key={order.order_id}>
        <span>{can(P.ordersView) ? <Link to={`/orders/${order.order_id}`}>{order.order_number}</Link> : <strong>{order.order_number}</strong>}<small>{order.customer_email ?? "Customer not provided"} · {formatDate(order.created_at)}</small></span>
        <Badge value={order.order_status} />
      </li>)}</ul> : <p className="muted">No recent orders.</p>}
    </section>
  </div>;
}

function DashboardOverview() {
  const { can } = useAuth();
  const canReport = can(P.reports);
  const [tab, setTab] = useState<Tab>("overview");
  const [period, setPeriod] = useState<DashboardPeriod>("last7");
  const tabId = useId();
  const range = dashboardPeriodRange(period);
  const week = currentWeekRange();
  const overview = useApi(() => getDashboardOverview(), []);
  const sales = useApi(() => canReport
    ? getReport<SalesReport>("sales", { start_date: range.start_date, end_date: range.end_date, group_by: "day" })
    : Promise.reject(new Error("Reports access required")), [range.start_date, range.end_date, canReport]);
  const inventory = useApi(() => canReport
    ? getReport<InventoryRow[]>("inventory", { stock_status: "all" })
    : Promise.reject(new Error("Reports access required")), [canReport]);
  const topWeek = useApi(() => canReport
    ? getReport<ProductSale[]>("sales-by-product", week)
    : Promise.reject(new Error("Reports access required")), [week.start_date, week.end_date, canReport]);
  const d = overview.data;
  const attention = d?.insights?.attention;
  const actionCount = attention ? attention.new_orders + attention.awaiting_packing + attention.awaiting_shipment : null;
  const outCount = inventory.data ? inventoryProducts(inventory.data).filter((product) => product.out).length : null;
  const todaySales = d?.insights?.comparison.today_revenue;
  const revenueChange = d?.insights?.comparison.revenue_vs_yesterday_pct;

  return <div className="cliq-dashboard">
    <div className="dashboard-top"><PageHeader title="Welcome back, Admin" subtitle="Store activity at a glance" /><PeriodSelect value={period} onChange={setPeriod} /></div>
    <div className="tabs dashboard-tabs" role="tablist" aria-label="Dashboard sections">
      {TABS.map((item, index) => <button key={item.value} type="button" role="tab" id={`${tabId}-${item.value}`} aria-controls={`${tabId}-${item.value}-panel`} aria-selected={tab === item.value} tabIndex={tab === item.value ? 0 : -1} className={tab === item.value ? "active" : undefined} onClick={() => setTab(item.value)} onKeyDown={(event) => {
        const next = event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : -1;
        if (next >= 0) { event.preventDefault(); setTab(TABS[next].value); document.getElementById(`${tabId}-${TABS[next].value}`)?.focus(); }
      }}>{item.label}</button>)}
    </div>
    {overview.error && <div className="status status-error" role="alert"><span>Dashboard data is unavailable: {overview.error}</span> <button type="button" className="link" onClick={overview.reload}>Try again</button></div>}
    {overview.loading && !d && <p className="state" role="status">Loading dashboard…</p>}
    {d && <>
      {tab === "overview" && <div role="tabpanel" id={`${tabId}-overview-panel`} aria-labelledby={`${tabId}-overview`} className="dashboard-overview-tab">
        <div className="stat-grid dashboard-overview-kpis">
          <Metric label="Today's booked order value" value={todaySales === undefined ? "Unavailable" : formatMoney(todaySales)} to={canReport ? "/reports" : undefined} hint={revenueChange === null || revenueChange === undefined ? "Excludes cancelled; not collected cash" : `${formatPct(revenueChange)} vs yesterday · not collected cash`} />
          <Metric label="Orders Today" value={d.orders.today} to={can(P.ordersView) ? `/orders?start_date=${dashboardPeriodRange("today").start_date}&end_date=${dashboardPeriodRange("today").end_date}` : undefined} hint="All order statuses" />
          <Metric label="Orders Needing Action" value={actionCount ?? "Unavailable"} to={can(P.ordersView) ? "/orders" : undefined} />
          <Metric label="Out-of-Stock Products" value={inventory.loading ? "Loading…" : outCount ?? "Unavailable"} to={can(P.catalogueView) ? "/inventory?stock_status=out" : undefined} hint="At least one variant out" />
        </div>
        <section className="panel dashboard-overview-revenue" aria-label="Overview revenue graph">
          <div className="panel-title"><h3>Booked order value · {DASHBOARD_PERIODS.find((option) => option.value === period)?.label}</h3><span className="muted">Non-cancelled orders · UTC · not collected cash</span></div>
          {sales.loading ? <p className="state" role="status">Loading order-value graph…</p>
            : sales.error || !sales.data ? <p className="state">Order-value graph unavailable. Report access is required.</p>
              : <DashboardTrend title="Booked order value trend" rows={sales.data.rows} metric="revenue" currency={sales.data.currency} />}
        </section>
        <ProductList title="Top-selling products this week" rows={topWeek.data} loading={topWeek.loading} error={topWeek.error} currency={sales.data?.currency} />
      </div>}
      {tab === "sales" && <div role="tabpanel" id={`${tabId}-sales-panel`} aria-labelledby={`${tabId}-sales`}><SalesPerformance range={range} report={sales.data} loading={sales.loading} error={sales.error} canReport={canReport} /></div>}
      {tab === "orders" && <div role="tabpanel" id={`${tabId}-orders-panel`} aria-labelledby={`${tabId}-orders`}><OrderOperations data={d} /></div>}
      {tab === "inventory" && <div role="tabpanel" id={`${tabId}-inventory-panel`} aria-labelledby={`${tabId}-inventory`}><DashboardInventory rows={inventory.data} loading={inventory.loading} error={inventory.error} /></div>}
    </>}
  </div>;
}

export default DashboardOverview;
