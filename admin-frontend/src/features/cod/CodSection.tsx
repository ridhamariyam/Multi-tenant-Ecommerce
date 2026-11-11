import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  getCodSettings,
  listCollections,
  recordRemittance,
  updateCodSettings,
} from "../../api/cod";
import { deletePincode, listPincodes, savePincode } from "../../api/shipping";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import ConfirmButton from "../../components/common/ConfirmButton";
import GuidedControl from "../../components/guidance/GuidedControl";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import Tabs from "../../components/common/Tabs";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { CodSettings, PincodeRule } from "../../types/settings";
import { emptyToNull, formatDate, formatMoney } from "../../utils/formatters";

type Tab = "settings" | "pincodes" | "collections";
const PIN = /^[1-9]\d{5}$/;
const NEW_PINCODE: PincodeRule = {
  pincode: "", is_serviceable: true, cod_available: true,
  min_delivery_days: null, max_delivery_days: null, shipping_amount: null, city: null, state: null,
};

function CodSection() {
  const [tab, setTab] = useState<Tab>("settings");
  return (
    <div className="record-page cod-page">
      <PageHeader title="Cash on delivery" subtitle="COD rules, pincode availability and cash reconciliation" />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { key: "settings", label: "Rules" },
          { key: "pincodes", label: "Pincodes" },
          { key: "collections", label: "Cash reconciliation" },
        ]}
      />
      {tab === "settings" && <CodRules />}
      {tab === "pincodes" && <CodPincodes />}
      {tab === "collections" && <Collections />}
    </div>
  );
}

function CodRules() {
  const settings = useApi(() => getCodSettings(), []);
  if (settings.error) return <div className="status status-error">{settings.error}</div>;
  if (!settings.data) return <div className="state">Loading…</div>;
  return <CodRulesForm initial={settings.data} />;
}

function CodRulesForm({ initial }: { initial: CodSettings }) {
  const { can } = useAuth();
  const canEdit = can(P.settingsManage);
  const [form, setForm] = useState<CodSettings>(initial);
  const [attempted, setAttempted] = useState(false);
  const action = useAction();
  const feeError = !form.fee_amount.trim() ? "COD fee is required." : Number(form.fee_amount) < 0 ? "COD fee cannot be negative." : null;

  const money = (k: keyof CodSettings) => (form[k] as string | null) ?? "";
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (feeError) return;
    setAttempted(false);
    action.run(async () => { const r = await updateCodSettings(form); setForm(r.data); }, "COD rules saved", "Could not save COD rules");
  };
  return (
    <form className="panel form" onSubmit={submit} noValidate>
      <StatusMessage status={action.status} />
      <p className="muted">Pincode COD availability can be managed in the Pincodes tab. Checkout checks the global switch, order limits, delivery and pincode restrictions; any restriction makes COD unavailable.</p>
      <GuidedControl className="guided-control--wide" hint="Turn off to stop offering COD at checkout, even where pincode rules allow it." dismissible><label className="check"><input type="checkbox" checked={form.is_enabled} disabled={!canEdit} onChange={(e) => setForm({ ...form, is_enabled: e.target.checked })} /> Offer cash on delivery</label></GuidedControl>
      <div className="form-grid">
        <Field label="Minimum order (₹)" hint="Blank = no minimum"><input type="number" min="0" step="0.01" disabled={!canEdit} value={money("min_order_amount")} onChange={(e) => setForm({ ...form, min_order_amount: emptyToNull(e.target.value) })} /></Field>
        <Field label="Maximum order (₹)" hint="Blank = no limit"><input type="number" min="0" step="0.01" disabled={!canEdit} value={money("max_order_amount")} onChange={(e) => setForm({ ...form, max_order_amount: emptyToNull(e.target.value) })} /></Field>
        <Field label="COD fee (₹)" required error={attempted ? feeError : null}><input type="number" min="0" step="0.01" disabled={!canEdit} value={form.fee_amount} onChange={(e) => setForm({ ...form, fee_amount: e.target.value })} /></Field>
        <Field label="Advance to pay online (₹)" hint="Partial-advance COD. Blank = none"><input type="number" min="0" step="0.01" disabled={!canEdit} value={money("advance_amount")} onChange={(e) => setForm({ ...form, advance_amount: emptyToNull(e.target.value) })} /></Field>
      </div>
      {attempted && feeError && <div className="status status-error" role="alert">Please correct the COD fee before continuing.</div>}
      {Number(form.advance_amount ?? 0) > 0 && <p className="muted">COD advances are confirmed manually under Payments.</p>}
      {canEdit && <div className="form-actions"><button className="primary" disabled={action.busy}>Save rules</button></div>}
    </form>
  );
}

function CodPincodes() {
  const { can } = useAuth();
  const canEdit = can(P.settingsManage);
  const [search, setSearch] = useState("");
  const [serviceable, setServiceable] = useState("");
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<PincodeRule | null>(null);
  const [isNew, setIsNew] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const action = useAction();
  const list = useApi(() => listPincodes({ search, is_serviceable: serviceable || undefined, page, page_size: 50 }), [search, serviceable, page]);

  const save = async (rule: PincodeRule) => {
    if (!PIN.test(rule.pincode)) return setError("Enter a valid 6-digit Indian pincode.");
    setError(null);
    if (isNew) {
      const existing = await action.run(() => listPincodes({ search: rule.pincode, page: 1, page_size: 50 }), null, "Could not check for an existing pincode");
      if (!existing) return;
      if (existing.data.some((item) => item.pincode === rule.pincode)) return setError("This pincode already has a rule. Edit its existing row instead.");
    }
    const { pincode, ...values } = rule;
    const saved = await action.run(() => savePincode(pincode, values), "Pincode COD rule saved", "Could not save pincode");
    if (saved) { setEditing(null); list.reload(); }
  };

  return <div className="panel record-table-panel cod-table-panel">
    <div className="panel-title">
      <div><h3>COD by pincode</h3><p className="muted">COD requires both a serviceable pincode and an allowed COD rule. Global COD limits still apply.</p></div>
      {canEdit && <button className="primary" onClick={() => { setError(null); setIsNew(true); setEditing(NEW_PINCODE); }}>Add pincode</button>}
    </div>
    <StatusMessage status={action.status} />
    <div className="filters">
      <GuidedControl className="guided-control--wide" hint="Find rules by pincode or its prefix."><input type="search" aria-label="Search pincode" placeholder="Search pincode prefix" maxLength={6} value={search} onChange={(e) => { setSearch(e.target.value.replace(/\D/g, "")); setPage(1); }} /></GuidedControl>
      <select aria-label="Delivery status" value={serviceable} onChange={(e) => { setServiceable(e.target.value); setPage(1); }}>
        <option value="">All delivery statuses</option><option value="true">Serviceable</option><option value="false">Not serviceable</option>
      </select>
      <Link to="/delivery">Full delivery settings</Link>
    </div>
    <DataTable
      rows={list.loading ? null : list.data} loading={list.loading} error={list.error}
      empty="No pincode rules match. Unlisted pincodes follow the Delivery defaults."
      rowKey={(rule) => rule.pincode}
      columns={[
        { key: "pincode", header: "Pincode" },
        { key: "place", header: "Location", render: (rule) => [rule.city, rule.state].filter(Boolean).join(", ") || "-" },
        { key: "is_serviceable", header: "Delivery", render: (rule) => <span className={`badge badge-${rule.is_serviceable ? "ok" : "bad"}`}>{rule.is_serviceable ? "Serviceable" : "Restricted"}</span> },
        { key: "cod_available", header: "COD", render: (rule) => <span className={`badge badge-${rule.cod_available && rule.is_serviceable ? "ok" : "bad"}`}>{rule.cod_available && rule.is_serviceable ? "Allowed" : "Restricted"}</span> },
        { key: "actions", header: "", render: (rule) => canEdit && <div className="toolbar">
          <button type="button" onClick={() => { setError(null); setIsNew(false); setEditing(rule); }}>Edit</button>
          <ConfirmButton message={`Remove the full pincode rule for ${rule.pincode}? This also removes its delivery and shipping overrides.`} onConfirm={() => action.run(async () => { await deletePincode(rule.pincode); list.reload(); }, "Pincode rule removed", "Could not remove pincode")}>Remove</ConfirmButton>
        </div> },
      ]}
    />
    <Pagination meta={list.loading ? null : list.meta} onPageChange={setPage} />
    {editing && <Modal title={editing.pincode ? `COD rule for ${editing.pincode}` : "Add pincode COD rule"} onClose={() => setEditing(null)} showCloseButton={false}>
      <form className="form" onSubmit={(event) => { event.preventDefault(); void save(editing); }}>
        <Field label="Pincode" required={isNew} error={error?.startsWith("Enter a valid") ? error : null}><input aria-label="Pincode" inputMode="numeric" maxLength={6} pattern="[1-9][0-9]{5}" disabled={!isNew} value={editing.pincode} onChange={(event) => { setError(null); setEditing({ ...editing, pincode: event.target.value.replace(/\D/g, "") }); }} /></Field>
        <label className="check"><input type="checkbox" checked={editing.cod_available} onChange={(event) => setEditing({ ...editing, cod_available: event.target.checked })} /> COD allowed for this pincode</label>
        {!editing.is_serviceable && <p className="muted">Delivery is disabled here, so COD remains unavailable even if this rule allows it.</p>}
        {error && <div className="status status-error" role="alert">{error}</div>}
        <div className="form-actions"><button type="button" onClick={() => setEditing(null)}>Cancel</button><button className="primary" disabled={action.busy}>Save pincode</button></div>
      </form>
    </Modal>}
  </div>;
}

function Collections() {
  const { can } = useAuth();
  const [status, setStatus] = useState<"outstanding" | "remitted">("outstanding");
  const [page, setPage] = useState(1);
  const list = useApi(() => listCollections({ status, page, page_size: 50 }), [status, page]);
  const [selected, setSelected] = useState<string[]>([]);
  const [reference, setReference] = useState("");
  const [remittedOn, setRemittedOn] = useState("");
  const action = useAction();
  const rows = list.data ?? [];
  const total = rows.filter((r) => selected.includes(r.payment_id)).reduce((sum, r) => sum + Number(r.amount), 0);
  const toggle = (id: string) => setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));

  return (
    <div className="panel record-table-panel cod-table-panel cod-collections">
      <p className="muted">Cash collected by the courier on delivered COD orders. Record a remittance when the courier pays it out.</p>
      <StatusMessage status={action.status} />
      <div className="filters">
        <select aria-label="Show" value={status} onChange={(e) => { setStatus(e.target.value as typeof status); setSelected([]); setPage(1); }}>
          <option value="outstanding">Not yet remitted</option>
          <option value="remitted">Remitted</option>
        </select>
      </div>
      <DataTable
        rows={list.loading ? null : list.data}
        loading={list.loading}
        error={list.error}
        empty={status === "outstanding" ? "No outstanding COD cash." : "No remittances recorded."}
        rowKey={(r) => r.payment_id}
        columns={[
          ...(status === "outstanding" && can(P.paymentsManage)
            ? [{ key: "sel", header: "", render: (r: (typeof rows)[number]) => <input type="checkbox" aria-label={`Select ${r.order_number}`} checked={selected.includes(r.payment_id)} onChange={() => toggle(r.payment_id)} /> }]
            : []),
          { key: "order_number", header: "Order", render: (r) => <Link to={`/orders/${r.order_id}`}>{r.order_number}</Link> },
          { key: "collected_at", header: "Collected", render: (r) => formatDate(r.collected_at) },
          { key: "amount", header: "Amount", align: "right", render: (r) => formatMoney(r.amount) },
          { key: "remitted_at", header: "Remitted", render: (r) => (r.remitted_at ? formatDate(r.remitted_at) : "-") },
          { key: "remittance_reference", header: "Reference", render: (r) => r.remittance_reference ?? "-" },
        ]}
      />
      <Pagination meta={list.loading ? null : list.meta} onPageChange={setPage} />
      {status === "outstanding" && can(P.paymentsManage) && (
        <form
          className="filters"
          style={{ marginTop: 8 }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!selected.length || !reference.trim()) return;
            action.run(async () => { await recordRemittance(selected, reference.trim(), remittedOn || null); setSelected([]); setReference(""); list.reload(); }, "Remittance recorded", "Could not record remittance");
          }}
        >
          <span>{selected.length} selected · {formatMoney(total)}</span>
          <input placeholder="Bank / UTR reference" value={reference} onChange={(e) => setReference(e.target.value)} aria-label="Reference" />
          <input type="date" value={remittedOn} onChange={(e) => setRemittedOn(e.target.value)} aria-label="Remitted on" />
          <button className="primary" disabled={!selected.length || !reference.trim() || action.busy}>Record remittance</button>
        </form>
      )}
    </div>
  );
}

export default CodSection;
