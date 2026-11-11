import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  addTrackingEvent,
  downloadInvoicePdf,
  downloadPackingSlip,
  downloadShippingLabel,
  getOrder,
  getTracking,
  listReturnReasons,
  updateAddress,
  updateShipment,
  updateStatus,
} from "../../api/orders";
import { markAdvancePaid } from "../../api/payments";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import DataTable from "../../components/common/DataTable";
import ConfirmDialog from "../../components/common/ConfirmDialog";
import Field from "../../components/common/Field";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import InvoiceModal from "./InvoiceModal";
import ShipmentPanel from "./ShipmentPanel";
import type { DeliveryAddress, Order, OrderStatus } from "../../types/order";
import { NEXT_STATUSES, SHIPPING_LABEL_STATUSES } from "../../types/order";
import { emptyToNull, formatDate, formatMoney, label } from "../../utils/formatters";
import "../detail-pages.css";

const ADDRESS_EDITABLE: OrderStatus[] = ["PENDING", "CONFIRMED", "PROCESSING", "PACKED"];
const SHIPPING_STATUSES: OrderStatus[] = ["SHIPPED", "OUT_FOR_DELIVERY"];
const ADVANCE_GATED_STATUSES: OrderStatus[] = ["CONFIRMED", "PROCESSING", "PACKED", "SHIPPED", "OUT_FOR_DELIVERY", "DELIVERED"];

function OrderDetail() {
  const { orderId = "" } = useParams();
  const { can } = useAuth();
  const order = useApi(() => getOrder(orderId), [orderId]);
  const tracking = useApi(() => getTracking(orderId), [orderId]);
  const action = useAction();
  const [showInvoice, setShowInvoice] = useState(false);
  const [editAddress, setEditAddress] = useState(false);

  const reload = () => {
    order.reload();
    tracking.reload();
  };
  const o = order.data;
  if (order.error) return <div className="status status-error">{order.error}</div>;
  if (!o) return <div className="state">Loading…</div>;

  const canManage = can(P.ordersManage);
  const currency = o.currency;
  const advance = o.payments.find((p) => p.purpose === "ADVANCE" && p.status === "PENDING");

  return (
    <div className="admin-detail-page order-detail-page">
      <PageHeader
        title={`Order ${o.order_number}`}
        subtitle={`Placed ${formatDate(o.created_at)}${o.is_guest ? " · guest checkout" : ""}`}
        actions={
          <>
            <Link to="/orders" className="btn">Back to orders</Link>
            <button onClick={() => setShowInvoice(true)}>GST invoice</button>
            <button disabled={action.busy} onClick={() => action.run(() => downloadInvoicePdf(o.id), null, "Invoice PDF failed")}>Invoice PDF</button>
            <button disabled={action.busy} onClick={() => action.run(() => downloadPackingSlip(o.id), null, "Packing slip failed")}>Packing slip</button>
            {SHIPPING_LABEL_STATUSES.includes(o.status) && <button disabled={action.busy} onClick={() => action.run(() => downloadShippingLabel(o.id), null, "Label failed")}>Shipping label</button>}
          </>
        }
      />
      <StatusMessage status={action.status} />

      <div className="order-detail-summary">
        <div className="panel order-detail-status">
          <h3>Status</h3>
          <dl className="kv">
            <dt>Order</dt><dd><Badge value={o.status} /></dd>
            <dt>Payment</dt><dd><Badge value={o.payment_status} /> {o.payment_method}</dd>
            <dt>Estimated delivery</dt><dd>{o.estimated_delivery_date ?? "-"}</dd>
            {o.status === "RETURNED" && (
              <>
                <dt>Return reason</dt>
                <dd>{o.return_reason ?? <span className="muted">Not recorded</span>}{o.return_note && <div className="muted">{o.return_note}</div>}</dd>
              </>
            )}
            <dt>Courier</dt><dd>{o.shipment.courier_name ?? "-"}</dd>
            <dt>Tracking</dt>
            <dd>{o.shipment.tracking_url ? <a href={o.shipment.tracking_url} target="_blank" rel="noreferrer">{o.shipment.tracking_number ?? "link"}</a> : o.shipment.tracking_number ?? "-"}</dd>
          </dl>
          {canManage && <StatusChanger key={o.status} order={o} onDone={reload} run={action.run} busy={action.busy} />}
        </div>
        <div className="panel order-detail-customer">
          <div className="panel-title">
            <h3>Customer &amp; delivery</h3>
            {canManage && ADDRESS_EDITABLE.includes(o.status) && <button className="link" onClick={() => setEditAddress(true)}>Edit address</button>}
          </div>
          <AddressBlock address={o.delivery_address} />
          <p>{o.contact_email ?? <span className="muted">No email</span>}</p>
          {can(P.customersView) && (
            <Link to={`/customers?search=${encodeURIComponent(o.delivery_address.phone.replace(/^\+91/, ""))}`}>Find customer record</Link>
          )}
        </div>
        <div className="panel order-detail-totals">
          <h3>Totals</h3>
          <dl className="kv">
            <dt>Subtotal</dt><dd className="num">{formatMoney(o.subtotal, currency)}</dd>
            <dt>Discount {o.coupon_code && `(${o.coupon_code})`}</dt><dd className="num">-{formatMoney(o.discount_amount, currency)}</dd>
            <dt>Shipping</dt><dd className="num">{formatMoney(o.shipping_amount, currency)}</dd>
            <dt>COD fee</dt><dd className="num">{formatMoney(o.cod_fee, currency)}</dd>
            <dt>Tax</dt><dd className="num">{formatMoney(o.tax_amount, currency)}</dd>
            {o.gst?.gst_type && (
              <>
                <dt>GST ({label(o.gst.gst_type)})</dt>
                <dd className="num">
                  {o.gst.gst_type === "INTRA_STATE"
                    ? `CGST ${o.gst.cgst_amount} + SGST ${o.gst.sgst_amount}`
                    : `IGST ${o.gst.igst_amount}`}
                </dd>
              </>
            )}
            <dt><strong>Total</strong></dt><dd className="num"><strong>{formatMoney(o.total_amount, currency)}</strong></dd>
            {Number(o.advance_amount) > 0 && (<><dt>COD advance</dt><dd className="num">{formatMoney(o.advance_amount, currency)}</dd></>)}
          </dl>
        </div>
      </div>

      <ShipmentPanel orderId={o.id} currency={currency} canManage={canManage} onDone={reload} />

      <div className="panel order-detail-items detail-table-panel">
        <h3>Items</h3>
        <DataTable
          rows={o.items}
          rowKey={(i) => i.variant_id}
          columns={[
            { key: "product_name", header: "Product", render: (i) => <Link to={`/products/${i.product_id}`}>{i.product_name}</Link> },
            { key: "variant_name", header: "Variant" },
            { key: "sku", header: "SKU" },
            { key: "hsn_code", header: "HSN" },
            { key: "quantity", header: "Qty", align: "right" },
            { key: "unit_price", header: "Unit price", align: "right", render: (i) => formatMoney(i.unit_price, currency) },
            { key: "gst_rate", header: "GST %", align: "right", render: (i) => i.gst_rate ?? "-" },
            { key: "subtotal", header: "Line total", align: "right", render: (i) => formatMoney(i.subtotal, currency) },
          ]}
        />
      </div>

      <div className="order-detail-secondary">
        <div className="panel order-detail-payments detail-table-panel">
          <h3>Payments</h3>
          <DataTable
            rows={o.payments}
            empty="No payment records."
            rowKey={(p) => p.id}
            columns={[
              { key: "purpose", header: "Purpose" },
              { key: "provider", header: "Method" },
              { key: "status", header: "Status", render: (p) => <Badge value={p.status} /> },
              { key: "amount", header: "Amount", align: "right", render: (p) => formatMoney(p.amount, p.currency) },
              { key: "remitted_at", header: "Remitted", render: (p) => (p.remitted_at ? `${formatDate(p.remitted_at)} (${p.remittance_reference})` : "-") },
            ]}
          />
          {advance && o.payment_method === "CASH_ON_DELIVERY" && !["CANCELLED", "RETURNED"].includes(o.status) && can(P.paymentsManage) && (
            <button
              disabled={action.busy}
              onClick={() => action.run(async () => { await markAdvancePaid(advance.id); reload(); }, "Advance marked as paid", "Could not mark advance paid")}
            >
              Mark COD advance received
            </button>
          )}
          <p className="muted">Online refunds are not available yet: no payment gateway is connected (see Integrations).</p>
        </div>
        <div className="panel order-detail-tracking">
          <h3>Tracking history</h3>
          {tracking.error && <div className="status status-error">{tracking.error}</div>}
          <ul className="list-plain timeline detail-scroll-list">
            {tracking.data?.events.map((e, idx) => (
              <li key={idx}>
                <span className="muted" style={{ minWidth: 150 }}>{formatDate(e.occurred_at)}</span>
                <span>{e.status && <Badge value={e.status} />} {e.description} {e.location && <span className="muted">· {e.location}</span>}</span>
              </li>
            ))}
          </ul>
          {can(P.ordersManage) && <TrackingForm orderId={o.id} order={o} onDone={reload} run={action.run} busy={action.busy} />}
        </div>
      </div>

      {showInvoice && <InvoiceModal orderId={o.id} onClose={() => setShowInvoice(false)} />}
      {editAddress && (
        <AddressModal
          address={o.delivery_address}
          onClose={() => setEditAddress(false)}
          onSave={async (address, reason) => {
            const ok = await action.run(() => updateAddress(o.id, { ...address, reason }), "Address updated", "Could not update address");
            if (ok) {
              setEditAddress(false);
              reload();
            }
          }}
        />
      )}
    </div>
  );
}

type Run = ReturnType<typeof useAction>["run"];

function StatusChanger({ order, onDone, run, busy }: { order: Order; onDone: () => void; run: Run; busy: boolean }) {
  const advancePending = Number(order.advance_amount) > 0 && !order.payments.some((payment) => payment.purpose === "ADVANCE" && payment.status === "PAID");
  const options = NEXT_STATUSES[order.status].filter((next) => !advancePending || !ADVANCE_GATED_STATUSES.includes(next));
  const [status, setStatus] = useState<OrderStatus | "">("");
  const [note, setNote] = useState("");
  const [courier, setCourier] = useState(order.shipment.courier_name ?? "");
  const [tracking, setTracking] = useState(order.shipment.tracking_number ?? "");
  const [url, setUrl] = useState(order.shipment.tracking_url ?? "");
  const [reasonId, setReasonId] = useState("");
  const [returnNote, setReturnNote] = useState("");
  const [confirmCancel, setConfirmCancel] = useState(false);
  const reasons = useApi(() => (options.includes("RETURNED") ? listReturnReasons(true) : Promise.resolve({ success: true, message: "", data: [], meta: null })), [order.status]);
  if (options.length === 0) return <p className="muted">This order is closed.</p>;

  const needsShipment = status !== "" && SHIPPING_STATUSES.includes(status);
  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!status || !options.includes(status)) return;
    if (status === "CANCELLED") {
      setConfirmCancel(true);
      return;
    }
    await save();
  };
  const save = async () => {
    if (!status || !options.includes(status)) return;
    const ok = await run(
      () =>
        updateStatus(order.id, status, {
          note: emptyToNull(note),
          ...(needsShipment ? { courier_name: emptyToNull(courier), tracking_number: emptyToNull(tracking), tracking_url: emptyToNull(url) } : {}),
          ...(status === "RETURNED" ? { return_reason_id: reasonId || null, return_note: emptyToNull(returnNote) } : {}),
        }),
      `Order moved to ${label(status)}`,
      "Status change failed"
    );
    if (ok) {
      setStatus("");
      setNote("");
      onDone();
    }
  };

  return (
    <form className="form" onSubmit={submit} style={{ marginTop: 12 }}>
      {confirmCancel && (
        <ConfirmDialog
          title="Cancel this order?"
          message="Its stock is released back to inventory and this cannot be undone."
          confirmLabel="Cancel order"
          onCancel={() => setConfirmCancel(false)}
          onConfirm={() => {
            setConfirmCancel(false);
            void save();
          }}
        />
      )}
      <Field label="Move to" required guidance="Choose the next valid fulfilment status for this order." guidanceDismissible>
        <select value={options.includes(status as OrderStatus) ? status : ""} onChange={(e) => setStatus(e.target.value as OrderStatus)}>
          <option value="">Choose next status…</option>
          {options.map((s) => <option key={s} value={s}>{label(s)}</option>)}
        </select>
      </Field>
      {advancePending && NEXT_STATUSES[order.status].some((next) => ADVANCE_GATED_STATUSES.includes(next)) && <p className="muted">Record the COD advance before moving this order forward.</p>}
      {needsShipment && (
        <>
          <Field label="Courier"><input value={courier} onChange={(e) => setCourier(e.target.value)} /></Field>
          <Field label="Tracking number"><input value={tracking} onChange={(e) => setTracking(e.target.value)} /></Field>
          <Field label="Tracking URL"><input type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></Field>
        </>
      )}
      {status === "RETURNED" && (
        <>
          <Field label="Return reason" hint={reasons.data?.length ? undefined : "Add reasons under Settings → Return reasons"}>
            <select value={reasonId} onChange={(e) => setReasonId(e.target.value)}>
              <option value="">Not recorded</option>
              {reasons.data?.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </Field>
          <Field label="Return details"><input value={returnNote} onChange={(e) => setReturnNote(e.target.value)} maxLength={500} /></Field>
        </>
      )}
      <Field label="Note (shown in tracking)"><input value={note} onChange={(e) => setNote(e.target.value)} maxLength={500} /></Field>
      <button className="primary" disabled={!status || !options.includes(status) || busy}>Update status</button>
    </form>
  );
}

function TrackingForm({ orderId, order, onDone, run, busy }: { orderId: string; order: Order; onDone: () => void; run: Run; busy: boolean }) {
  const [description, setDescription] = useState("");
  const [location, setLocation] = useState("");
  const [courier, setCourier] = useState(order.shipment.courier_name ?? "");
  const [number, setNumber] = useState(order.shipment.tracking_number ?? "");
  const [url, setUrl] = useState(order.shipment.tracking_url ?? "");
  return (
    <>
      {order.status !== "CANCELLED" && <form
        className="form"
        onSubmit={async (e) => {
          e.preventDefault();
          if (!description.trim()) return;
          const ok = await run(() => addTrackingEvent(orderId, { description: description.trim(), location: emptyToNull(location) }), "Tracking update added", "Could not add tracking update");
          if (ok) {
            setDescription("");
            setLocation("");
            onDone();
          }
        }}
      >
        <h4>Add tracking update</h4>
        <div className="form-grid">
          <Field label="Update" required><input value={description} onChange={(e) => setDescription(e.target.value)} required maxLength={500} /></Field>
          <Field label="Location"><input value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
        </div>
        <button disabled={busy || !description.trim()}>Add update</button>
      </form>}
      <form
        className="form"
        style={{ marginTop: 12 }}
        onSubmit={async (e) => {
          e.preventDefault();
          const ok = await run(() => updateShipment(orderId, { courier_name: emptyToNull(courier), tracking_number: emptyToNull(number), tracking_url: emptyToNull(url) }), "Shipment details saved", "Could not save shipment details");
          if (ok) onDone();
        }}
      >
        <h4>Shipment details</h4>
        <div className="form-grid">
          <Field label="Courier"><input value={courier} onChange={(e) => setCourier(e.target.value)} /></Field>
          <Field label="Tracking number"><input value={number} onChange={(e) => setNumber(e.target.value)} /></Field>
          <Field label="Tracking URL"><input type="url" value={url} onChange={(e) => setUrl(e.target.value)} /></Field>
        </div>
        <button disabled={busy}>Save shipment</button>
      </form>
    </>
  );
}

function AddressBlock({ address }: { address: DeliveryAddress }) {
  return (
    <address style={{ fontStyle: "normal" }}>
      <strong>{address.full_name}</strong><br />
      {address.phone}<br />
      {address.address_line_1}<br />
      {address.address_line_2 && <>{address.address_line_2}<br /></>}
      {address.city}, {address.state} {address.postal_code}<br />
      {address.country}
    </address>
  );
}

function AddressModal({ address, onClose, onSave }: { address: DeliveryAddress; onClose: () => void; onSave: (a: DeliveryAddress, reason: string | null) => void }) {
  const [form, setForm] = useState<DeliveryAddress>(address);
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const set = (k: keyof DeliveryAddress) => (e: ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value });
  const validate = () => {
    const problems: Record<string, string> = {};
    for (const [key, title] of [["full_name", "Full name"], ["phone", "Phone"], ["address_line_1", "Address line 1"], ["city", "City"], ["state", "State"], ["country", "Country"]] as const) {
      if (!form[key]?.trim()) problems[key] = `${title} is required.`;
    }
    if (!/^\d{6}$/.test(form.postal_code.trim())) problems.postal_code = "Enter a valid 6-digit pincode.";
    return problems;
  };
  const fieldErrors = attempted ? validate() : {};
  return (
    <Modal title="Edit delivery address" onClose={onClose} showCloseButton={false}>
      <form className="form" onSubmit={(e) => { e.preventDefault(); setAttempted(true); if (Object.keys(validate()).length === 0) onSave({ ...form, address_line_2: emptyToNull(form.address_line_2 ?? "") }, emptyToNull(reason)); }} noValidate>
        <p className="muted">Allowed until the order ships. A change of state that would switch GST between CGST/SGST and IGST is refused.</p>
        <div className="form-grid">
          <Field label="Full name" required error={fieldErrors.full_name}><input value={form.full_name} onChange={set("full_name")} /></Field>
          <Field label="Phone" required error={fieldErrors.phone}><input value={form.phone} onChange={set("phone")} /></Field>
          <Field label="Address line 1" required error={fieldErrors.address_line_1} wide><input value={form.address_line_1} onChange={set("address_line_1")} /></Field>
          <Field label="Address line 2" wide><input value={form.address_line_2 ?? ""} onChange={set("address_line_2")} /></Field>
          <Field label="City" required error={fieldErrors.city}><input value={form.city} onChange={set("city")} /></Field>
          <Field label="State" required error={fieldErrors.state}><input value={form.state} onChange={set("state")} /></Field>
          <Field label="Pincode" required error={fieldErrors.postal_code} hint="6 digits"><input value={form.postal_code} onChange={set("postal_code")} /></Field>
          <Field label="Country" required error={fieldErrors.country}><input value={form.country} onChange={set("country")} /></Field>
          <Field label="Reason (shown in tracking)" wide><input value={reason} onChange={(e) => setReason(e.target.value)} /></Field>
        </div>
        {attempted && Object.keys(fieldErrors).length > 0 && <div className="status status-error" role="alert">Please complete all required fields before continuing.</div>}
        <div className="form-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="primary">Save address</button>
        </div>
      </form>
    </Modal>
  );
}


export default OrderDetail;
