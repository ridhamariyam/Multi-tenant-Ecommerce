import { useState } from "react";
import type { FormEvent } from "react";
import { bulkPincodes, deletePincode, getShipping, listPincodes, savePincode, updateShipping } from "../../api/shipping";
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
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { PincodeRule, ShippingSettings } from "../../types/settings";
import { emptyToNull, formatMoney } from "../../utils/formatters";
import { PIN, parsePincodeCsv } from "./pincodeCsv";
import ProviderSettings from "./ProviderSettings";
import "./shipping.css";


function ShippingSection() {
  const { can } = useAuth();
  const canEdit = can(P.settingsManage);
  return (
    <div className="delivery-page">
      <PageHeader title="Delivery" subtitle="Shipping charges, delivery estimates and serviceable pincodes" />
      <ProviderSettings canEdit={canEdit} />
      <ShippingRules canEdit={canEdit} />
      <Pincodes canEdit={canEdit} />
    </div>
  );
}

function ShippingRules({ canEdit }: { canEdit: boolean }) {
  const settings = useApi(() => getShipping(), []);
  if (settings.error) return <div className="status status-error">{settings.error}</div>;
  if (!settings.data) return <div className="state">Loading…</div>;
  return <ShippingRulesForm initial={settings.data} canEdit={canEdit} />;
}

function ShippingRulesForm({ initial, canEdit }: { initial: ShippingSettings; canEdit: boolean }) {
  const [form, setForm] = useState<ShippingSettings>(initial);
  const [attempted, setAttempted] = useState(false);
  const action = useAction();
  const chargeError = !form.shipping_amount.trim() ? "Shipping charge is required." : Number(form.shipping_amount) < 0 ? "Shipping charge cannot be negative." : null;
  const daysError = form.min_delivery_days > form.max_delivery_days ? "Minimum days cannot exceed maximum days." : null;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (chargeError || daysError) return;
    setAttempted(false);
    action.run(async () => { const r = await updateShipping(form); setForm(r.data); }, "Delivery settings saved", "Could not save");
  };
  return (
    <form className="panel form" onSubmit={submit} noValidate>
      <h3>Default delivery rules</h3>
      <StatusMessage status={action.status} />
      <fieldset disabled={!canEdit} className="form" style={{ border: 0, padding: 0, margin: 0 }}>
        <div className="form-grid">
          <Field label="Shipping charge (₹)" required error={attempted ? chargeError : null} guidance="Set the default delivery charge when no pincode rule overrides it." guidanceDismissible><input type="number" min="0" step="0.01" value={form.shipping_amount} onChange={(e) => setForm({ ...form, shipping_amount: e.target.value })} /></Field>
          <Field label="Free shipping above (₹)" hint="Blank = never free"><input type="number" min="0" step="0.01" value={form.free_shipping_minimum ?? ""} onChange={(e) => setForm({ ...form, free_shipping_minimum: emptyToNull(e.target.value) })} /></Field>
          <Field label="Delivery in (min days)" error={attempted ? daysError : null}><input type="number" min="0" value={form.min_delivery_days} onChange={(e) => setForm({ ...form, min_delivery_days: Number(e.target.value) })} /></Field>
          <Field label="Delivery in (max days)"><input type="number" min="0" value={form.max_delivery_days} onChange={(e) => setForm({ ...form, max_delivery_days: Number(e.target.value) })} /></Field>
        </div>
        <label className="check"><input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Charge shipping</label>
        <label className="check"><input type="checkbox" checked={form.restrict_to_listed_pincodes} onChange={(e) => setForm({ ...form, restrict_to_listed_pincodes: e.target.checked })} /> Deliver only to pincodes listed below</label>
      </fieldset>
      {attempted && (chargeError || daysError) && <div className="status status-error" role="alert">Please correct the delivery rules before continuing.</div>}
      {canEdit && <div className="form-actions"><button className="primary" disabled={action.busy}>Save</button></div>}
    </form>
  );
}

const EMPTY_RULE: PincodeRule = { pincode: "", is_serviceable: true, cod_available: true, min_delivery_days: null, max_delivery_days: null, shipping_amount: null, city: null, state: null };

function Pincodes({ canEdit }: { canEdit: boolean }) {
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const list = useApi(() => listPincodes({ search, page }), [search, page]);
  const action = useAction();
  const [editing, setEditing] = useState<PincodeRule | null>(null);
  const [bulk, setBulk] = useState(false);

  return (
    <div className="panel delivery-pincodes-panel">
      <div className="panel-title">
        <h3>Pincodes</h3>
        {canEdit && <div className="toolbar"><button onClick={() => setBulk(true)}>Bulk add</button><button className="primary" onClick={() => setEditing(EMPTY_RULE)}>Add pincode</button></div>}
      </div>
      <StatusMessage status={action.status} />
      <div className="filters"><GuidedControl className="guided-control--wide" hint="Find a delivery rule by pincode or city."><input type="search" placeholder="Search pincode or city" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }} /></GuidedControl></div>
      <DataTable
        rows={list.data}
        loading={list.loading}
        error={list.error}
        empty="No pincode rules. Every pincode uses the defaults above."
        rowKey={(r) => r.pincode}
        onRowClick={canEdit ? setEditing : undefined}
        columns={[
          { key: "pincode", header: "Pincode" },
          { key: "city", header: "City / state", render: (r) => [r.city, r.state].filter(Boolean).join(", ") || "-" },
          { key: "is_serviceable", header: "Delivers", render: (r) => (r.is_serviceable ? "Yes" : "No") },
          { key: "cod_available", header: "COD", render: (r) => (r.cod_available ? "Yes" : "No") },
          { key: "eta", header: "Days", render: (r) => (r.min_delivery_days !== null ? `${r.min_delivery_days}–${r.max_delivery_days}` : "default") },
          { key: "shipping_amount", header: "Shipping", render: (r) => (r.shipping_amount ? formatMoney(r.shipping_amount) : "default") },
          { key: "x", header: "", render: (r) => canEdit && <ConfirmButton message={`Remove the rule for ${r.pincode}?`} onConfirm={() => action.run(async () => { await deletePincode(r.pincode); list.reload(); }, "Removed", "Could not remove")}>Remove</ConfirmButton> },
        ]}
      />
      <Pagination meta={list.meta} onPageChange={setPage} />
      {editing && <PincodeModal rule={editing} busy={action.busy} onClose={() => setEditing(null)} onSave={async (r) => { const ok = await action.run(() => savePincode(r.pincode, withoutPincode(r)), "Pincode saved", "Could not save pincode"); if (ok) { setEditing(null); list.reload(); } }} />}
      {bulk && <BulkModal busy={action.busy} onClose={() => setBulk(false)} onSave={async (rules) => { const ok = await action.run(() => bulkPincodes(rules), `${rules.length} pincodes saved`, "Bulk save failed"); if (ok) { setBulk(false); list.reload(); } }} />}
    </div>
  );
}

function withoutPincode(rule: PincodeRule): Omit<PincodeRule, "pincode"> {
  const { pincode: _pincode, ...rest } = rule;
  void _pincode;
  return rest;
}

function PincodeModal({ rule, busy, onClose, onSave }: { rule: PincodeRule; busy: boolean; onClose: () => void; onSave: (r: PincodeRule) => void }) {
  const [r, setR] = useState(rule);
  const [attempted, setAttempted] = useState(false);
  const isNew = rule.pincode === "";
  const pincodeError = !PIN.test(r.pincode) ? "Enter a valid 6-digit pincode." : null;
  const daysError = (r.min_delivery_days === null) !== (r.max_delivery_days === null) ? "Give both min and max days, or neither." : r.min_delivery_days !== null && r.max_delivery_days !== null && r.min_delivery_days > r.max_delivery_days ? "Min days cannot exceed max days." : null;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setAttempted(true);
    if (pincodeError || daysError) return;
    onSave({ ...r, city: emptyToNull(r.city ?? ""), state: emptyToNull(r.state ?? "") });
  };
  const num = (v: string) => (v === "" ? null : Number(v));
  return (
    <Modal title={isNew ? "Add pincode" : `Pincode ${rule.pincode}`} onClose={onClose} showCloseButton={false}>
      <form className="form" onSubmit={submit} noValidate>
        <div className="form-grid">
          <Field label="Pincode" required={isNew} error={attempted ? pincodeError : null}><input value={r.pincode} disabled={!isNew} onChange={(e) => setR({ ...r, pincode: e.target.value.trim() })} /></Field>
          <Field label="City"><input value={r.city ?? ""} onChange={(e) => setR({ ...r, city: e.target.value || null })} /></Field>
          <Field label="State"><input value={r.state ?? ""} onChange={(e) => setR({ ...r, state: e.target.value || null })} /></Field>
          <Field label="Min days" required={r.max_delivery_days !== null} error={attempted ? daysError : null} hint="Blank = default"><input type="number" min="0" value={r.min_delivery_days ?? ""} onChange={(e) => setR({ ...r, min_delivery_days: num(e.target.value) })} /></Field>
          <Field label="Max days" required={r.min_delivery_days !== null} error={attempted ? daysError : null}><input type="number" min="0" value={r.max_delivery_days ?? ""} onChange={(e) => setR({ ...r, max_delivery_days: num(e.target.value) })} /></Field>
          <Field label="Shipping (₹)" hint="Blank = default"><input type="number" min="0" step="0.01" value={r.shipping_amount ?? ""} onChange={(e) => setR({ ...r, shipping_amount: emptyToNull(e.target.value) })} /></Field>
        </div>
        <label className="check"><input type="checkbox" checked={r.is_serviceable} onChange={(e) => setR({ ...r, is_serviceable: e.target.checked })} /> We deliver here</label>
        <label className="check"><input type="checkbox" checked={r.cod_available} onChange={(e) => setR({ ...r, cod_available: e.target.checked })} /> Cash on delivery available</label>
        {attempted && (pincodeError || daysError) && <div className="status status-error" role="alert">Please correct the pincode rule before continuing.</div>}
        <div className="form-actions"><button type="button" onClick={onClose}>Cancel</button><button className="primary" disabled={busy}>Save</button></div>
      </form>
    </Modal>
  );
}

function BulkModal({ busy, onClose, onSave }: { busy: boolean; onClose: () => void; onSave: (rules: PincodeRule[]) => void }) {
  const [text, setText] = useState("");
  const parsed = parsePincodeCsv(text);
  return (
    <Modal title="Bulk add pincodes" onClose={onClose} showCloseButton={false} wide>
      <div className="form">
        <p className="muted">One pincode per line: <code>pincode,serviceable,cod,min_days,max_days,shipping,city,state</code>. Only the pincode is required; blanks use the defaults. Existing pincodes are updated. Up to 1000 per save.</p>
        <textarea rows={10} value={text} onChange={(e) => setText(e.target.value)} placeholder={"560001,yes,yes,2,4,,Bengaluru,Karnataka\n682001"} />
        <p>{parsed.rules.length} valid lines{parsed.errors.length > 0 && `, ${parsed.errors.length} problems`}</p>
        {parsed.errors.length > 0 && <ul className="status status-error">{parsed.errors.slice(0, 10).map((e) => <li key={e}>{e}</li>)}</ul>}
        <div className="form-actions"><button onClick={onClose}>Cancel</button><button className="primary" disabled={busy || parsed.rules.length === 0 || parsed.errors.length > 0 || parsed.rules.length > 1000} onClick={() => onSave(parsed.rules)}>Save {parsed.rules.length} pincodes</button></div>
      </div>
    </Modal>
  );
}

export default ShippingSection;
