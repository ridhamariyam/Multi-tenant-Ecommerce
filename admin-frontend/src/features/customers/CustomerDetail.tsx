import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { addCustomerNote, deleteCustomerNote, getCustomer, getCustomerOrders, setCustomerTags, setOrderBlock } from "../../api/customers";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import StatCard from "../../components/common/StatCard";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import { formatDate, formatMoney } from "../../utils/formatters";
import "../detail-pages.css";

function CustomerDetail() {
  const { customerId = "" } = useParams();
  const navigate = useNavigate();
  const { can } = useAuth();
  const canManage = can(P.customersManage);
  const [page, setPage] = useState(1);
  const customer = useApi(() => getCustomer(customerId), [customerId]);
  const orders = useApi(() => getCustomerOrders(customerId, page), [customerId, page]);
  const action = useAction();
  const [tagInput, setTagInput] = useState("");
  const [note, setNote] = useState("");
  const [tagAttempted, setTagAttempted] = useState(false);
  const [noteAttempted, setNoteAttempted] = useState(false);
  const [blockReason, setBlockReason] = useState("");
  const [confirmBlock, setConfirmBlock] = useState(false);

  const c = customer.data;
  if (customer.error) return <div className="status status-error">{customer.error}</div>;
  if (!c) return <div className="state">Loading…</div>;

  const saveTags = (tags: string[]) =>
    action.run(async () => { await setCustomerTags(c.id, tags); customer.reload(); }, "Tags saved", "Could not save tags");

  return (
    <div className="admin-detail-page customer-detail-page">
      <PageHeader title={c.name ?? c.email ?? c.phone ?? "Customer"} subtitle={`Customer since ${formatDate(c.created_at)}`} actions={<Link className="btn" to="/customers">Back to customers</Link>} />
      <StatusMessage status={action.status} />
      {c.order_blocked && (
        <div className="status status-error" role="status">
          Blocked from placing orders{c.order_block_reason ? `: ${c.order_block_reason}` : ""} (since {formatDate(c.order_blocked_at)}). Past orders are unaffected.
        </div>
      )}
      {confirmBlock && (
        <ConfirmDialog
          title="Block this customer?"
          message="They won't be able to place new orders, with their account or as a guest using this phone number. Past orders are not changed."
          confirmLabel="Block ordering"
          onCancel={() => setConfirmBlock(false)}
          onConfirm={() => {
            setConfirmBlock(false);
            action.run(async () => { await setOrderBlock(c.id, true, blockReason.trim() || null); setBlockReason(""); customer.reload(); }, "Customer blocked from ordering", "Could not block");
          }}
        />
      )}
      {canManage && (
        <div className="panel customer-detail-ordering">
          <h3>Ordering</h3>
          {c.order_blocked ? (
            <ConfirmButton
              className="primary"
              message="Allow this customer to place orders again?"
              onConfirm={() => action.run(async () => { await setOrderBlock(c.id, false, null); customer.reload(); }, "Customer can order again", "Could not unblock")}
            >
              Unblock ordering
            </ConfirmButton>
          ) : (
            <form
              className="toolbar"
              onSubmit={(e) => {
                e.preventDefault();
                setConfirmBlock(true);
              }}
            >
              <input placeholder="Reason (staff only)" value={blockReason} onChange={(e) => setBlockReason(e.target.value)} maxLength={200} style={{ width: 260 }} aria-label="Block reason" />
              <button className="danger" disabled={action.busy}>Block ordering</button>
            </form>
          )}
          <p className="muted">This is separate from the COD blocklist, which only stops cash on delivery for a phone number.</p>
        </div>
      )}
      <div className="stat-grid customer-detail-metrics">
        <StatCard label="Orders" value={c.total_orders} hint={`${c.cancelled_orders} cancelled · ${c.returned_orders} returned`} />
        <StatCard label="Total spent" value={formatMoney(c.total_spent, c.currency)} />
        <StatCard label="Last order" value={formatDate(c.last_order_at)} />
        <StatCard label="Type" value={c.is_returning ? "Returning" : c.total_orders === 1 ? "New" : "No orders"} />
      </div>

      <div className="customer-detail-main">
        <div className="panel customer-detail-contact">
          <h3>Contact</h3>
          <dl className="kv">
            <dt>Phone</dt><dd>{c.phone ?? "—"}</dd>
            <dt>Email</dt><dd>{c.email ?? "-"}</dd>
            <dt>Status</dt><dd><Badge value={c.status} /> {c.is_verified ? "verified" : "not verified"}</dd>
          </dl>
          <h4 style={{ marginTop: 16 }}>Addresses</h4>
          {c.addresses.length === 0 && <p className="muted">No saved addresses.</p>}
          <ul className="list-plain detail-scroll-list customer-address-list">
            {c.addresses.map((a) => (
              <li key={a.id}>
                {a.full_name}, {a.address_line_1}{a.address_line_2 ? `, ${a.address_line_2}` : ""}, {a.city}, {a.state} {a.postal_code} {a.is_default && <Badge value="DEFAULT" />}
              </li>
            ))}
          </ul>
          <h4 style={{ marginTop: 16 }}>Tags</h4>
          <div className="chips">
            {c.tags.length === 0 && <span className="muted">No tags</span>}
            {c.tags.map((t) => (
              <span className="chip" key={t}>
                {t}
                {canManage && <button aria-label={`Remove ${t}`} onClick={() => saveTags(c.tags.filter((x) => x !== t))}>×</button>}
              </span>
            ))}
          </div>
          {canManage && (
            <form className="toolbar" style={{ marginTop: 8 }} onSubmit={(e) => { e.preventDefault(); setTagAttempted(true); const t = tagInput.trim(); if (t) { saveTags([...c.tags, t]); setTagInput(""); setTagAttempted(false); } }} noValidate>
              <Field label="New tag" required error={tagAttempted && !tagInput.trim() ? "Tag name is required." : null}><input value={tagInput} onChange={(e) => setTagInput(e.target.value)} placeholder="e.g. VIP" maxLength={40} style={{ width: 200 }} /></Field>
              <button disabled={action.busy}>Add tag</button>
            </form>
          )}
        </div>
        <div className="panel customer-detail-notes">
          <h3>Internal notes</h3>
          <p className="muted">Visible to staff only.</p>
          {canManage && (
            <form className="form" onSubmit={(e) => { e.preventDefault(); setNoteAttempted(true); const body = note.trim(); if (!body) return; action.run(async () => { await addCustomerNote(c.id, body); setNote(""); setNoteAttempted(false); customer.reload(); }, "Note added", "Could not add note"); }} noValidate>
              <Field label="Note" required error={noteAttempted && !note.trim() ? "Note is required." : null} guidance="Record staff-only context that may help with future orders." guidanceDismissible><textarea value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000} placeholder="e.g. Prefers evening delivery" /></Field>
              <button disabled={action.busy}>Add note</button>
            </form>
          )}
          <ul className="list-plain detail-scroll-list customer-note-list">
            {c.notes.length === 0 && <li className="muted">No notes yet.</li>}
            {c.notes.map((n) => (
              <li key={n.id}>
                <div>{n.body}</div>
                <small className="muted">{n.author_name ?? "Former staff"} · {formatDate(n.created_at)}</small>{" "}
                {canManage && <ConfirmButton className="link" message="Delete this note?" onConfirm={() => action.run(async () => { await deleteCustomerNote(c.id, n.id); customer.reload(); }, "Note deleted", "Could not delete note")}>Delete</ConfirmButton>}
              </li>
            ))}
          </ul>
          <p className="muted">Customer messaging (email/WhatsApp) needs a provider to be connected — see Integrations.</p>
        </div>
      </div>

      <div className="panel customer-detail-history detail-table-panel">
        <h3>Order history</h3>
        <DataTable
          rows={orders.data}
          loading={orders.loading}
          error={orders.error}
          empty="This customer has not ordered yet."
          rowKey={(o) => o.id}
          onRowClick={(o) => navigate(`/orders/${o.id}`)}
          columns={[
            { key: "order_number", header: "Order", render: (o) => <Link to={`/orders/${o.id}`} onClick={(event) => event.stopPropagation()}>{o.order_number}</Link> },
            { key: "created_at", header: "Placed", render: (o) => formatDate(o.created_at) },
            { key: "status", header: "Status", render: (o) => <Badge value={o.status} /> },
            { key: "payment_status", header: "Payment", render: (o) => <Badge value={o.payment_status} /> },
            { key: "total_amount", header: "Total", align: "right", render: (o) => formatMoney(o.total_amount, o.currency) },
          ]}
        />
        <Pagination meta={orders.meta} onPageChange={setPage} />
      </div>
    </div>
  );
}

export default CustomerDetail;
