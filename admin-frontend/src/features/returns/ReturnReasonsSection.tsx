import { useState } from "react";
import { createReturnReason, listReturnReasons, updateReturnReason } from "../../api/orders";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import Badge from "../../components/common/Badge";
import ConfirmButton from "../../components/common/ConfirmButton";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import "./returnReasons.css";

const SUGGESTED_REASONS = [
  "Size too small",
  "Size too large",
  "Product damaged or defective",
  "Wrong item received",
  "Product differs from description",
  "Colour or appearance differs",
  "Customer refused delivery",
  "Other",
];

// The store's own list. Orders keep the label they were returned with, so editing
// or switching off a reason never changes past orders.
function ReturnReasonsSection() {
  const { can } = useAuth();
  const canEdit = can(P.settingsManage);
  const reasons = useApi(() => listReturnReasons(), []);
  const action = useAction();
  const [label, setLabel] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [editing, setEditing] = useState<{ id: string; label: string } | null>(null);
  const existing = new Set((reasons.data ?? []).map((reason) => reason.label.trim().toLowerCase()));
  const missingSuggestions = SUGGESTED_REASONS.filter((reason) => !existing.has(reason.toLowerCase()));

  return (
    <div className="return-reasons-page record-page">
      <PageHeader title="Return reasons" subtitle="Chosen when an order is marked returned; grouped in the returns report" />
      <StatusMessage status={action.status} />
      {canEdit && (
        <form
          className="filters return-reasons-controls"
          onSubmit={(e) => {
            e.preventDefault();
            setAttempted(true);
            if (!label.trim()) return;
            action.run(async () => { await createReturnReason(label.trim()); setLabel(""); setAttempted(false); reasons.reload(); }, "Reason added", "Could not add reason");
          }}
        >
          <Field label="New reason" required error={attempted && !label.trim() ? "Return reason is required." : null} guidance="Add a reason customers can choose when returning an order." guidanceDismissible><input placeholder="e.g. Refused at delivery" value={label} onChange={(e) => setLabel(e.target.value)} maxLength={100} /></Field>
          <button className="primary" disabled={action.busy}>Add reason</button>
          {reasons.data && missingSuggestions.length > 0 && <button type="button" disabled={action.busy} onClick={() => action.run(async () => {
            try {
              for (const suggestion of missingSuggestions) await createReturnReason(suggestion);
            } finally { reasons.reload(); }
          }, "Suggested reasons added", "Could not add all suggested reasons")}>Add {missingSuggestions.length} suggested reasons</button>}
        </form>
      )}
      <div className="panel return-reasons-table-panel">
        <DataTable
          rows={reasons.data}
          loading={reasons.loading}
          error={reasons.error}
          empty="No return reasons yet."
          rowKey={(r) => r.id}
          columns={[
            {
              key: "label",
              header: "Reason",
              render: (r) =>
                editing?.id === r.id ? (
                  <form
                    className="toolbar"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (!editing.label.trim()) return;
                      action.run(async () => { await updateReturnReason(r.id, { label: editing.label.trim() }); setEditing(null); reasons.reload(); }, "Reason renamed", "Could not rename");
                    }}
                  >
                    <input value={editing.label} onChange={(e) => setEditing({ id: r.id, label: e.target.value })} aria-label="Reason label" maxLength={100} />
                    <button>Save</button>
                    <button type="button" onClick={() => setEditing(null)}>Cancel</button>
                  </form>
                ) : (
                  r.label
                ),
            },
            { key: "is_active", header: "Status", render: (r) => <Badge value={r.is_active ? "ACTIVE" : "INACTIVE"} /> },
            {
              key: "x",
              header: "",
              render: (r) =>
                canEdit && (
                  <div className="toolbar">
                    <button onClick={() => setEditing({ id: r.id, label: r.label })}>Rename</button>
                    {r.is_active ? <ConfirmButton className="" disabled={action.busy} message={`Deactivate ${r.label}? Past orders keep their saved reason, and this reason will no longer be available for new returns.`} onConfirm={() => action.run(async () => { await updateReturnReason(r.id, { is_active: false }); reasons.reload(); }, "Reason switched off", "Could not update")}>Deactivate</ConfirmButton>
                      : <button type="button" disabled={action.busy} onClick={() => action.run(async () => { await updateReturnReason(r.id, { is_active: true }); reasons.reload(); }, "Reason switched on", "Could not update")}>Activate</button>}
                  </div>
                ),
            },
          ]}
        />
      </div>
    </div>
  );
}

export default ReturnReasonsSection;
