import { useState } from "react";
import { Link } from "react-router-dom";
import { getReport } from "../../api/reports";
import { listPayments } from "../../api/payments";
import { getCodReport } from "../../api/cod";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import StatCard from "../../components/common/StatCard";
import DataTable from "../../components/common/DataTable";
import Pagination from "../../components/common/Pagination";
import PageHeader from "../../components/common/PageHeader";
import GuidedControl from "../../components/guidance/GuidedControl";
import Tabs from "../../components/common/Tabs";
import { useApi } from "../../hooks/useApi";
import { formatDate, formatMoney, formatPct, label } from "../../utils/formatters";
import { BarChart, DonutChart, TrendChart } from "./ReportCharts";
import { columnsFor } from "./ReportColumns";
import { ReportExports } from "./ReportExports";
import ReportTable from "./ReportTable";
import type { ReportRow as Row } from "./ReportTable";
import "./reports.css";
export { ExportButtons } from "./ReportExports";

type Tab = "overview" | "sales" | "products" | "customers" | "payments" | "returns";
type Period = "today" | "yesterday" | "week" | "month" | "this-month" | "custom";
type Range = { start_date: string; end_date: string };
type SalesData = { rows: Row[]; summary: Row; currency?: string };
type CustomerData = Row & { top_customers: Row[] };
type ReturnData = Row & { by_product: Row[]; by_reason: Row[] };
const DAY = 86400000;
const iso = (date: Date) => date.toISOString().slice(0, 10);
const today = () => new Date(`${iso(new Date())}T00:00:00Z`);
const daysBefore = (date: Date, days: number) => iso(new Date(date.getTime() - days * DAY));
function periodRange(period: Period): Range {
  const now = today();
  const end_date = iso(now);
  if (period === "today") return { start_date: end_date, end_date };
  if (period === "yesterday") { const yesterday = daysBefore(now, 1); return { start_date: yesterday, end_date: yesterday }; }
  if (period === "week") return { start_date: daysBefore(now, 6), end_date };
  if (period === "this-month") return { start_date: `${end_date.slice(0, 7)}-01`, end_date };
  return { start_date: daysBefore(now, 29), end_date };
}
function previousRange(range: Range): Range {
  const length = Math.round((Date.parse(range.end_date) - Date.parse(range.start_date)) / DAY) + 1;
  const start = new Date(`${range.start_date}T00:00:00Z`);
  return { start_date: daysBefore(start, length), end_date: daysBefore(start, 1) };
}
const rangeValid = (range: Range) => !!range.start_date && !!range.end_date && range.start_date <= range.end_date && (Date.parse(range.end_date) - Date.parse(range.start_date)) / DAY <= 366;
const money = (value: Row[string] | undefined, currency?: string) => value == null ? "Unavailable" : formatMoney(value, currency);
const number = (value: Row[string] | undefined) => value == null ? "Unavailable" : String(value);

function ReportsSection() {
  const [tab, setTab] = useState<Tab>("overview");
  const [period, setPeriod] = useState<Period>("month");
  const [range, setRange] = useState<Range>(() => periodRange("month"));
  const [compare, setCompare] = useState(false);
  const valid = rangeValid(range);
  const setQuick = (next: Period) => { setPeriod(next); if (next !== "custom") setRange(periodRange(next)); };
  return <div className="cliq-reports">
    <PageHeader title="Reports & analytics" subtitle="Store trends and report details" />
    <Tabs active={tab} onChange={setTab} tabs={[
      { key: "overview", label: "Overview" }, { key: "sales", label: "Sales" }, { key: "products", label: "Products" },
      { key: "customers", label: "Customers" }, { key: "payments", label: "Payments" }, { key: "returns", label: "Returns" },
    ]} />
    <div className="reports-range" aria-label="Report date range">
      <GuidedControl hint="Choose the period used by the charts and report totals." dismissible><select aria-label="Quick date range" value={period} onChange={(e) => setQuick(e.target.value as Period)}>
        <option value="today">Today</option><option value="yesterday">Yesterday</option><option value="week">Last 7 Days</option>
        <option value="month">Last 30 Days</option><option value="this-month">This Month</option><option value="custom">Custom Range</option>
      </select></GuidedControl>
      <GuidedControl className="guided-control--date" hint="Set the first day of a custom report."><label>From <input aria-label="From" type="date" value={range.start_date} max={range.end_date} onChange={(e) => { setPeriod("custom"); setRange({ ...range, start_date: e.target.value }); }} /></label></GuidedControl>
      <GuidedControl className="guided-control--date" hint="Set the last day of a custom report."><label>To <input aria-label="To" type="date" value={range.end_date} min={range.start_date} onChange={(e) => { setPeriod("custom"); setRange({ ...range, end_date: e.target.value }); }} /></label></GuidedControl>
      {(tab === "overview" || tab === "sales") && <label className="reports-compare"><input type="checkbox" checked={compare} onChange={(e) => setCompare(e.target.checked)} /> Compare previous period</label>}
      <span className="reports-range-note">UTC dates</span>
    </div>
    {!valid ? <p role="alert" className="status status-error">Choose a valid date range of at most 366 days.</p> : <>
      {tab === "overview" && <Overview range={range} compare={compare} />}
      {tab === "sales" && <Sales range={range} compare={compare} />}
      {tab === "products" && <Products range={range} period={period} />}
      {tab === "customers" && <Customers range={range} />}
      {tab === "payments" && <Payments range={range} />}
      {tab === "returns" && <Returns range={range} />}
    </>}
  </div>;
}

function PreviousSales({ range, groupBy = "day", children }: { range: Range; groupBy?: string; children: (data: SalesData | null, loading: boolean) => React.ReactNode }) {
  const prior = previousRange(range);
  const report = useApi(() => getReport<SalesData>("sales", { ...prior, group_by: groupBy }), [prior.start_date, prior.end_date, groupBy]);
  return <>{report.error && <p className="muted">Previous-period comparison is unavailable.</p>}{children(report.error ? null : report.data, report.loading)}</>;
}

function RevenuePanel({ rows, range, compare, title }: { rows: Row[]; range: Range; compare: boolean; title: string }) {
  return <div className="panel reports-revenue"><div className="panel-title"><h3>{title}</h3><span className="muted">{range.start_date} – {range.end_date}</span></div>
    {compare ? <PreviousSales range={range}>{(prior, loading) => <>{loading && <p className="muted">Loading comparison…</p>}<TrendChart title="Booked order value comparison" rows={rows} compare={prior?.rows} field="revenue" currency /></>}</PreviousSales> : <TrendChart title="Booked order value trend" rows={rows} field="revenue" currency />}
  </div>;
}

function Overview({ range, compare }: { range: Range; compare: boolean }) {
  const sales = useApi(() => getReport<SalesData>("sales", { ...range, group_by: "day" }), [range.start_date, range.end_date]);
  const analytics = useApi(() => getReport<Row & { top_products: Row[] }>("analytics", range), [range.start_date, range.end_date]);
  const summary = sales.data?.summary;
  return <>
    <div className="reports-kpis stat-grid">
      <StatCard label="Gross sales" value={sales.loading ? "Loading…" : money(summary?.subtotal, sales.data?.currency)} hint="Order subtotals before discounts and tax" />
      <StatCard label="Net booked sales" value={sales.loading ? "Loading…" : money(summary?.net_revenue, sales.data?.currency)} hint="Order value less returned parcels; not collected funds" />
      <StatCard label="Total orders" value={sales.loading ? "Loading…" : number(summary?.orders)} hint="Excludes cancelled orders" />
      <StatCard label="Average order value" value={sales.loading ? "Loading…" : money(summary?.average_order_value, sales.data?.currency)} />
      <StatCard label="Refunds" value="Unavailable" hint="Refund amounts are not reported by the API" />
      <StatCard label="Discounts" value={sales.loading ? "Loading…" : money(summary?.discount, sales.data?.currency)} />
    </div>
    {sales.error && <p role="alert" className="status status-error">{sales.error}</p>}
    {sales.loading ? <div className="panel state">Loading order-value trend…</div> : sales.data && <RevenuePanel rows={sales.data.rows} range={range} compare={compare} title="Booked order value" />}
    <div className="reports-secondary">
      <div className="panel">{sales.loading ? <p className="muted">Loading order trend…</p> : sales.error ? <p className="muted">Order trend unavailable.</p> : <TrendChart title="Orders trend" rows={sales.data?.rows ?? []} field="orders" />}</div>
      <div className="panel"><h3>Prepaid vs COD orders</h3>{analytics.error ? <p className="muted">Payment split unavailable.</p> : analytics.loading ? <p className="muted">Loading…</p> : <DonutChart title="Order payment type" parts={[{ label: "Prepaid", value: Number(analytics.data?.prepaid_orders) || 0, color: "var(--accent)" }, { label: "COD", value: Number(analytics.data?.cod_orders) || 0, color: "var(--chart-secondary)" }]} />}</div>
      <div className="panel"><h3>Top-performing products</h3>{analytics.error ? <p className="muted">Product ranking unavailable.</p> : analytics.loading ? <p className="muted">Loading…</p> : <BarChart title="Top products by revenue" rows={analytics.data?.top_products ?? []} labelKey="product_name" valueKey="net_sales" currency />}</div>
      <div className="panel"><h3>New vs returning customers</h3>{analytics.error ? <p className="muted">Customer split unavailable.</p> : analytics.loading ? <p className="muted">Loading…</p> : <BarChart title="Customers who ordered" rows={[{ name: "New", count: analytics.data?.new_customers ?? 0 }, { name: "Returning", count: analytics.data?.returning_customers ?? 0 }]} labelKey="name" valueKey="count" />}</div>
    </div>
  </>;
}

function Sales({ range, compare }: { range: Range; compare: boolean }) {
  const [groupBy, setGroupBy] = useState("day");
  const [breakdown, setBreakdown] = useState<"sales-by-product" | "sales-by-category" | "sales-by-location">("sales-by-product");
  const [locationLevel, setLocationLevel] = useState("state");
  const query = { ...range, group_by: groupBy };
  const report = useApi(() => getReport<SalesData>("sales", query), [range.start_date, range.end_date, groupBy]);
  const d = report.data;
  return <>
    <div className="reports-inline-controls"><label>Group order value <select aria-label="Group by" value={groupBy} onChange={(e) => setGroupBy(e.target.value)}><option value="day">Daily</option><option value="week">Weekly</option><option value="month">Monthly</option></select></label>
      <ReportExports name="sales" query={query} rows={d?.rows ?? []} />
    </div>
    {report.error && <p role="alert" className="status status-error">{report.error}</p>}
    {report.loading ? <div className="state">Loading sales…</div> : d && <>
      <div className="reports-kpis stat-grid">
        <StatCard label="Gross sales" value={money(d.summary.subtotal, d.currency)} hint="Subtotal before discounts and tax" />
      <StatCard label="Net booked sales" value={money(d.summary.net_revenue, d.currency)} hint="Order value less returned parcels; not collected funds" />
        <StatCard label="Discounts" value={money(d.summary.discount, d.currency)} /><StatCard label="Taxes" value={money(d.summary.tax, d.currency)} />
        <StatCard label="Orders" value={number(d.summary.orders)} /><StatCard label="AOV" value={money(d.summary.average_order_value, d.currency)} /><StatCard label="Refunds" value="Unavailable" hint="No refund amount in API" />
      </div>
      <div className="reports-chart-grid">
        {compare ? <PreviousSales range={range} groupBy={groupBy}>{(prior) => <TrendChart title="Booked order value comparison" rows={d.rows} compare={prior?.rows} field="revenue" currency />}</PreviousSales> : <TrendChart title="Booked order value trend" rows={d.rows} field="revenue" currency />}
        <TrendChart title="Order volume" rows={d.rows} field="orders" />
        <TrendChart title="Average order value" rows={d.rows} field="average_order_value" currency />
      </div>
      <p className="reports-footnote">These sales figures are booked order value, not collected payments. Refund transaction amounts are unavailable; returned parcel value is excluded from net booked sales.</p>
    </>}
    <div className="reports-inline-controls"><label>Sales breakdown <select aria-label="Sales breakdown" value={breakdown} onChange={(e) => setBreakdown(e.target.value as typeof breakdown)}><option value="sales-by-product">Product</option><option value="sales-by-category">Category</option><option value="sales-by-location">Location</option></select></label>
      {breakdown === "sales-by-location" && <label>Location level <select aria-label="Location level" value={locationLevel} onChange={(e) => setLocationLevel(e.target.value)}><option value="state">State</option><option value="city">City</option></select></label>}
    </div>
    <Breakdown key={`${breakdown}:${locationLevel}:${range.start_date}:${range.end_date}`} name={breakdown} range={range} level={locationLevel} />
  </>;
}

function Breakdown({ name, range, level }: { name: "sales-by-product" | "sales-by-category" | "sales-by-location"; range: Range; level: string }) {
  const query = name === "sales-by-location" ? { ...range, level } : range;
  const report = useApi(() => getReport<Row[]>(name, query), [name, range.start_date, range.end_date, level]);
  const rows = report.data ?? [];
  const labelKey = name === "sales-by-product" ? "product_name" : name === "sales-by-category" ? "category_name" : "state";
  const valueKey = name === "sales-by-location" ? "revenue" : "net_sales";
  return <div className="panel">{report.loading ? <p className="muted">Loading breakdown…</p> : report.error ? null : <BarChart title={`Sales by ${name.replace("sales-by-", "")}`} rows={rows} labelKey={labelKey} valueKey={valueKey} currency />}
    <ReportTable name={name} query={query} rows={report.data} loading={report.loading} error={report.error} empty="No sales for this period." rowKey={(row) => String(row.product_id ?? row.category_id ?? `${row.state}:${row.city}`)} columns={columnsFor(rows, ["product_id", "category_id"])} />
  </div>;
}

function Products({ range, period }: { range: Range; period: Period }) {
  const query = range;
  const report = useApi(() => getReport<Row[]>("sales-by-product", query), [range.start_date, range.end_date]);
  const rows = report.data ?? [];
  const unsoldDays = period === "week" ? 7 : period === "month" ? 30 : null;
  return <>
    <div className="panel">{report.loading ? <p className="muted">Loading product chart…</p> : report.error ? null : <BarChart title="Best-selling products by revenue" rows={rows} labelKey="product_name" valueKey="net_sales" currency />}
      <ReportTable key={`${range.start_date}:${range.end_date}`} heading={<h3>Product performance</h3>} name="sales-by-product" query={query} rows={report.data} loading={report.loading} error={report.error} empty="No product sales in this period." rowKey={(row) => String(row.product_id)} columns={columnsFor(rows, ["product_id"])} />
    </div>
    <div className="reports-two-col"><div className="panel"><CategorySummary range={range} /></div><div className="panel">
      <h3>Lowest and unsold products</h3>
      <p className="muted">The sales API returns only its 100 highest-revenue products, so a complete lowest-selling ranking is unavailable.</p>
      {unsoldDays ? <Unsold days={unsoldDays} /> : <p className="muted">The no-sales API supports rolling 7 or 30 days here; it cannot match this selected date range.</p>}
    </div></div>
  </>;
}
function CategorySummary({ range }: { range: Range }) {
  const report = useApi(() => getReport<Row[]>("sales-by-category", range), [range.start_date, range.end_date]);
  return <>{report.loading ? <p className="muted">Loading categories…</p> : report.error ? <p role="alert" className="status status-error">{report.error}</p> : <BarChart title="Category performance" rows={report.data ?? []} labelKey="category_name" valueKey="net_sales" currency />}</>;
}
function Unsold({ days }: { days: number }) {
  const report = useApi(() => getReport<Row[]>("unsold", { days }), [days]);
  const rows = report.data ?? [];
  return <ReportTable key={days} heading={<h4>No sales in last {days} days</h4>} name="unsold" query={{ days }} rows={report.data} loading={report.loading} error={report.error} empty="No unsold products found." rowKey={(row) => String(row.variant_id)} columns={columnsFor(rows, ["product_id", "variant_id"])} />;
}

function Customers({ range }: { range: Range }) {
  const canViewDetails = useAuth().can(P.customersView);
  const query = { ...range, top: 100 };
  const report = useApi(() => getReport<CustomerData>("customers", query), [range.start_date, range.end_date]);
  const d = report.data;
  return <>{report.error && <p role="alert" className="status status-error">{report.error}</p>}
    {report.loading ? <div className="state">Loading customers…</div> : d && <>
      <div className="reports-kpis stat-grid"><StatCard label="Customers who ordered" value={number(d.customers_ordering)} /><StatCard label="New customers" value={number(d.new_customers)} /><StatCard label="Returning customers" value={number(d.returning_customers)} hint={formatPct(d.returning_pct as number | null)} /><StatCard label="Sign-ups" value={number(d.signups)} /></div>
      <div className="reports-two-col"><div className="panel"><BarChart title="New vs returning customers" rows={[{ name: "New", count: d.new_customers }, { name: "Returning", count: d.returning_customers }]} labelKey="name" valueKey="count" /></div><div className="panel"><p className="muted">Acquisition is based on first orders in the selected period. Individual order frequency over time requires a backend aggregate.</p><p className="muted">Spending and order counts in the table cover the selected dates.</p></div></div>
      <div className="panel"><ReportTable key={`${range.start_date}:${range.end_date}`} heading={<h3>Top 100 customers by spending</h3>} name="customers" query={query} rows={d.top_customers} empty="No customers ordered in this period." rowKey={(row) => String(row.customer_id)} columns={[
        { key: "customer_id", header: "Customer ID", render: (row: Row) => canViewDetails ? <Link className="report-customer-id" to={`/customers/${row.customer_id}`} title={String(row.customer_id)}>{String(row.customer_id)}</Link> : <span className="report-customer-id">{String(row.customer_id)}</span> },
        { key: "name", header: "Customer", render: (row: Row) => canViewDetails ? <Link to={`/customers/${row.customer_id}`}>{row.name ?? "View customer"}</Link> : String(row.name ?? "—") },
        ...columnsFor(d.top_customers, ["customer_id", "name", "email", "phone"]),
      ]} /></div>
    </>}
  </>;
}

function Payments({ range }: { range: Range }) {
  const canView = useAuth().can(P.paymentsView);
  return <>{canView ? <PaymentRecords /> : <p className="state">Payment records require payments.view permission.</p>}<div className="reports-two-col"><PaymentSplit range={range} /><CodSummary range={range} /></div></>;
}
function PaymentRecords() {
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("");
  const query = { page, page_size: 50, status };
  const rows = useApi(() => listPayments(query), [page, status]);
  const counts = useApi(async () => {
    const statuses = ["PAID", "PENDING", "FAILED", "REFUNDED"];
    const results = await Promise.all(statuses.map((value) => listPayments({ page: 1, page_size: 1, status: value })));
    return { success: true, message: "", data: Object.fromEntries(statuses.map((value, i) => [value, results[i].meta?.total_items ?? null])), meta: null };
  }, []);
  return <>
    <p className="reports-footnote">Payment records and status totals are all-time. The payment API does not support date filtering or transaction trends.</p>
    {counts.error && <p role="alert" className="status status-error">{counts.error}</p>}
    <div className="reports-kpis stat-grid">{["PAID", "PENDING", "FAILED", "REFUNDED"].map((key) => <StatCard key={key} label={`${label(key)} payments`} value={counts.loading ? "Loading…" : number(counts.data?.[key] ?? null)} hint="Records, all-time" />)}</div>
    <div className="panel"><div className="reports-inline-controls"><h3>Payment records</h3><select aria-label="Payment status" value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }}><option value="">All statuses</option>{["PENDING", "PROCESSING", "PAID", "FAILED", "CANCELLED", "REFUND_PENDING", "REFUNDED", "PARTIALLY_REFUNDED", "EXPIRED"].map((value) => <option key={value} value={value}>{label(value)}</option>)}</select></div>
      <ReportExports query={query} rows={rows.data ?? []} pageOnly filename={`payments-page-${page}`} />
      <DataTable rows={rows.loading ? null : rows.data} loading={rows.loading} error={rows.error} empty="No payments match this status." rowKey={(row) => row.id} columns={[
        { key: "id", header: "Payment ID" }, { key: "created_at", header: "Date", render: (row) => formatDate(row.created_at) },
        { key: "order_id", header: "Order", render: (row) => <Link to={`/orders/${row.order_id}`}>{row.order_id.slice(0, 8)}</Link> },
        { key: "provider", header: "Provider" }, { key: "purpose", header: "Purpose" }, { key: "status", header: "Status" },
        { key: "amount", header: "Amount", render: (row) => formatMoney(row.amount, row.currency) },
      ]} />
      {!rows.loading && !rows.error && <Pagination meta={rows.meta} onPageChange={setPage} />}
    </div>
  </>;
}
function PaymentSplit({ range }: { range: Range }) {
  const report = useApi(() => getReport<Row>("analytics", range), [range.start_date, range.end_date]);
  const d = report.data;
  return <div className="panel"><h3>Prepaid vs COD orders · selected period</h3><p className="muted">Order payment type, not card, UPI, bank or settled cash.</p>
    {report.error ? <p role="alert" className="status status-error">{report.error}</p> : report.loading ? <div className="state">Loading…</div> : <DonutChart title="Prepaid and COD order distribution" parts={[{ label: "Prepaid", value: Number(d?.prepaid_orders) || 0, color: "var(--accent)" }, { label: "COD", value: Number(d?.cod_orders) || 0, color: "var(--chart-secondary)" }]} />}
  </div>;
}
function CodSummary({ range }: { range: Range }) {
  const report = useApi(() => getCodReport(range.start_date, range.end_date), [range.start_date, range.end_date]);
  const d = report.data;
  const completed = d ? Number(d.delivered_orders) + Number(d.returned_orders) : 0;
  return <div className="panel"><h3>COD collection · selected period</h3>
    {report.error ? <p role="alert" className="status status-error">{report.error}</p> : report.loading ? <div className="state">Loading…</div> : d && <div className="reports-mini-kpis stat-grid">
      <StatCard label="Cash collected" value={formatMoney(d.cash_collected)} />
      <StatCard label="Returned COD orders" value={d.returned_orders} />
      <StatCard label="COD parcel return rate" value={formatPct(completed ? Number(d.returned_orders) / completed * 100 : null)} />
    </div>}
  </div>;
}

function Returns({ range }: { range: Range }) {
  const report = useApi(() => getReport<ReturnData>("returns", range), [range.start_date, range.end_date]);
  const d = report.data;
  return <>{report.error && <p role="alert" className="status status-error">{report.error}</p>}
    {report.loading ? <div className="state">Loading returns…</div> : d && <>
      <p className="reports-footnote">This API reports undelivered returned parcels (RTO), not customer return requests or refund transactions.</p>
      <div className="reports-kpis stat-grid"><StatCard label="Returned parcels" value={number(d.returned_orders)} /><StatCard label="Parcel return rate" value={formatPct(d.return_rate as number | null)} hint="Returned / (returned + delivered)" /><StatCard label="Returned parcel value" value={money(d.returned_value)} hint="Not a refunded amount" /><StatCard label="Refund amount" value="Unavailable" hint="Refund ledger is not reported" /></div>
      <div className="reports-two-col"><div className="panel"><BarChart title="Most returned products" rows={d.by_product} labelKey="product_name" valueKey="units_returned" /></div><div className="panel"><BarChart title="Returned parcels by reason" rows={d.by_reason} labelKey="reason" valueKey="orders" /></div></div>
      <div className="reports-two-col"><div className="panel"><ReportTable key={`reason:${range.start_date}:${range.end_date}`} heading={<h3>Return reasons</h3>} name="returns" query={{ ...range, breakdown: "reason" }} rows={d.by_reason} empty="No returned parcels in this period." rowKey={(row) => String(row.reason)} columns={columnsFor(d.by_reason)} /></div>
        <div className="panel"><ReportTable key={`product:${range.start_date}:${range.end_date}`} heading={<h3>Returned products</h3>} name="returns" query={{ ...range, breakdown: "product" }} rows={d.by_product} empty="No returned products in this period." rowKey={(row) => String(row.product_id)} columns={columnsFor(d.by_product, ["product_id"])} /></div></div>
      <p className="reports-footnote">Approval statuses, refund trends and time-series return trends require backend reporting support.</p>
    </>}
  </>;
}

export default ReportsSection;
