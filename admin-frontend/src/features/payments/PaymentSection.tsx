import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { fetchAllPages } from "../../api/client";
import { listPayments, markAdvancePaid } from "../../api/payments";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import GuidedControl from "../../components/guidance/GuidedControl";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { PageMeta } from "../../types/api";
import type { Payment } from "../../types/order";
import { formatDate, formatMoney, label } from "../../utils/formatters";
import "./payments.css";

const PAGE_SIZE = 20;
const FETCH_SIZE = 100;
const MAIN_STATUSES = ["PENDING", "PAID", "FAILED", "REFUND_PENDING", "REFUNDED"];
const OTHER_STATUSES = ["PROCESSING", "CANCELLED", "PARTIALLY_REFUNDED", "EXPIRED"];
const providerLabel = (provider: string) => ({ COD: "COD", PREPAID: "Manual prepaid", RAZORPAY: "Razorpay" })[provider as "COD" | "PREPAID" | "RAZORPAY"] ?? label(provider);

function utcDate(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toISOString().slice(0, 10);
}

function PaymentSection() {
  const { can } = useAuth();
  const [status, setStatus] = useState("");
  const [method, setMethod] = useState("");
  const [purpose, setPurpose] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Payment | null>(null);
  const action = useAction();

  const payments = useApi(() => fetchAllPages((page) => listPayments({ page, page_size: FETCH_SIZE }), "payment records"), []);

  const loading = payments.loading;
  const records = payments.data;
  const dateError = startDate && endDate && endDate < startDate ? "End date must be on or after start date." : null;
  const availableStatuses = [...MAIN_STATUSES, ...OTHER_STATUSES.filter((candidate) => records?.some((row) => row.status === candidate) || status === candidate)];
  const dateRows = useMemo(() => records?.filter((row) => {
    const date = utcDate(row.created_at);
    return (!startDate || date >= startDate) && (!endDate || date <= endDate);
  }) ?? [], [records, startDate, endDate]);
  const filtered = useMemo(() => dateRows.filter((row) =>
    (!status || row.status === status) &&
    (!method || row.provider === method) &&
    (!purpose || row.purpose === purpose) &&
    (!search || row.id.toLowerCase().includes(search.trim().toLowerCase()) || row.order_id.toLowerCase().includes(search.trim().toLowerCase()))
  ), [dateRows, status, method, purpose, search]);
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, totalPages);
  const meta: PageMeta | null = records && !dateError ? { page: currentPage, page_size: PAGE_SIZE, total_items: filtered.length, total_pages: totalPages } : null;
  const rows = records && !dateError ? filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE) : null;
  const currency = dateRows[0]?.currency ?? "INR";
  const paidAmount = dateRows.filter((row) => row.status === "PAID").reduce((sum, row) => sum + Number(row.amount), 0);
  const hasPartialRefunds = dateRows.some((row) => row.status === "PARTIALLY_REFUNDED");
  const refundedAmount = dateRows.filter((row) => row.status === "REFUNDED").reduce((sum, row) => sum + Number(row.amount), 0);
  const clearFilters = () => { setStatus(""); setMethod(""); setPurpose(""); setStartDate(""); setEndDate(""); setSearch(""); setPage(1); };
  const change = (setter: (value: string) => void, value: string) => { setter(value); setPage(1); };

  return (
    <div className="record-page payments-page">
      <PageHeader title="Payments" subtitle="Payment records for every order (COD, COD advance and prepaid)" />
      <StatusMessage status={action.status} />
      <div className="payment-summaries" aria-label="Payment summary">
        {[
          ["Paid payment amount", records ? formatMoney(paidAmount, currency) : "—", "Paid records created in selected UTC range"],
          ["Successful payments", records ? String(dateRows.filter((row) => row.status === "PAID").length) : "—", ""],
          ["Pending payments", records ? String(dateRows.filter((row) => row.status === "PENDING").length) : "—", ""],
          ["Failed payments", records ? String(dateRows.filter((row) => row.status === "FAILED").length) : "—", ""],
          ["Refunded amount", records && !hasPartialRefunds ? formatMoney(refundedAmount, currency) : "—", hasPartialRefunds ? "Partial refund amounts unavailable" : "Fully refunded records"],
        ].map(([title, value, hint]) => <div className="payment-summary" key={title}><span>{title}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</div>)}
      </div>
      <div className="filters payment-filters">
        <GuidedControl className="guided-control--wide" hint="Find a payment by its ID or related order ID." dismissible><input type="search" aria-label="Search payment or order ID" placeholder="Payment or order ID" value={search} onChange={(event) => change(setSearch, event.target.value)} /></GuidedControl>
        <GuidedControl hint="Filter by the payment record's current status."><select aria-label="Payment status" value={status} onChange={(event) => change(setStatus, event.target.value)}>
          <option value="">All statuses</option>
          {availableStatuses.map((item) => <option key={item} value={item}>{label(item)}</option>)}
        </select></GuidedControl>
        <GuidedControl hint="Filter by the payment record's actual provider."><select aria-label="Payment method" value={method} onChange={(event) => change(setMethod, event.target.value)}>
          <option value="">All providers</option><option value="COD">COD</option><option value="PREPAID">Manual prepaid</option><option value="RAZORPAY">Razorpay</option>
        </select></GuidedControl>
        <GuidedControl hint="Separate full, advance and balance payments."><select aria-label="Payment purpose" value={purpose} onChange={(event) => change(setPurpose, event.target.value)}>
          <option value="">All purposes</option><option value="FULL">Full</option><option value="ADVANCE">Advance</option><option value="BALANCE">Balance</option>
        </select></GuidedControl>
        <GuidedControl className="guided-control--date" hint="Start of the payment record's creation date range (UTC)."><label className="payment-date">From <input aria-label="Payment from date" type="date" value={startDate} max={endDate || undefined} onChange={(event) => change(setStartDate, event.target.value)} /></label></GuidedControl>
        <GuidedControl className="guided-control--date" hint="End of the payment record's creation date range (UTC)."><label className="payment-date">To <input aria-label="Payment to date" type="date" value={endDate} min={startDate || undefined} onChange={(event) => change(setEndDate, event.target.value)} /></label></GuidedControl>
        <button type="button" onClick={clearFilters} disabled={!status && !method && !purpose && !startDate && !endDate && !search}>Clear Filters</button>
      </div>
      {dateError && <div className="status status-error" role="alert">{dateError}</div>}
      <div className="panel record-table-panel payment-table-panel">
        <DataTable
          rows={rows}
          loading={loading}
          error={loading ? null : payments.error}
          onRetry={payments.reload}
          empty={filtered.length === 0 && (status || method || purpose || startDate || endDate || search) ? "No payments match these filters." : "No payment records yet."}
          rowKey={(payment) => payment.id}
          columns={[
            { key: "id", header: "Payment ID", render: (payment) => <button type="button" className="link payment-id" title={payment.id} onClick={() => setSelected(payment)}>{payment.id.length > 13 ? `${payment.id.slice(0, 8)}…${payment.id.slice(-4)}` : payment.id}</button> },
            { key: "created_at", header: "Payment Date", render: (payment) => formatDate(payment.created_at) },
            { key: "order_id", header: "Order", render: (payment) => <Link to={`/orders/${payment.order_id}`} title={payment.order_id}>View order</Link> },
            { key: "provider", header: "Provider", render: (payment) => providerLabel(payment.provider) },
            { key: "purpose", header: "Purpose", render: (payment) => label(payment.purpose) },
            { key: "status", header: "Status", render: (payment) => <Badge value={payment.status} /> },
            { key: "amount", header: "Amount", align: "right", render: (payment) => formatMoney(payment.amount, payment.currency) },
            { key: "actions", header: "", render: (payment) => payment.purpose === "ADVANCE" && payment.status === "PENDING" && can(P.paymentsManage) ? (
              <ConfirmButton className="" message="Confirm the COD advance was received?" disabled={action.busy} onConfirm={() => action.run(async () => { await markAdvancePaid(payment.id); payments.reload(); }, "Advance marked as paid", "Could not update payment")}>Mark advance received</ConfirmButton>
            ) : null },
          ]}
        />
        <Pagination meta={meta} onPageChange={setPage} />
      </div>
      {selected && <Modal title="Payment details" onClose={() => setSelected(null)}>
        <dl className="kv payment-details">
          <dt>Payment ID</dt><dd><code>{selected.id}</code></dd>
          <dt>Order</dt><dd><Link to={`/orders/${selected.order_id}`}>View order</Link></dd>
          <dt>Created</dt><dd>{formatDate(selected.created_at)}</dd>
          <dt>Provider</dt><dd>{providerLabel(selected.provider)}</dd>
          <dt>Purpose</dt><dd>{label(selected.purpose)}</dd>
          <dt>Status</dt><dd><Badge value={selected.status} /></dd>
          <dt>Amount</dt><dd>{formatMoney(selected.amount, selected.currency)}</dd>
          {selected.remitted_at && <><dt>Remitted</dt><dd>{formatDate(selected.remitted_at)}</dd></>}
          {selected.remittance_reference && <><dt>Reference</dt><dd>{selected.remittance_reference}</dd></>}
        </dl>
      </Modal>}
    </div>
  );
}

export default PaymentSection;
