import { useState } from "react";
import { adjustStock, listMovements, setStock, setThreshold } from "../../api/variants";
import DataTable from "../../components/common/DataTable";
import Field from "../../components/common/Field";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { Variant } from "../../types/catalogue";
import { emptyToNull } from "../../utils/formatters";

const REASONS = ["ADJUSTMENT", "RESTOCK"];

// Stock controls for one variant. Sellable = available - reserved; checkout refuses more than that.
function InventoryPanel({ variant, canManage, onChanged }: { variant: Variant; canManage: boolean; onChanged: () => void }) {
  const inv = variant.inventory;
  const [page, setPage] = useState(1);
  const movements = useApi(() => listMovements(variant.id, page), [variant.id, page]);
  const action = useAction();
  const [delta, setDelta] = useState("");
  const [reason, setReason] = useState("RESTOCK");
  const [note, setNote] = useState("");
  const [exact, setExact] = useState("");
  const [alertAt, setAlertAt] = useState(String(inv?.low_stock_threshold ?? 0));

  const done = () => { movements.reload(); onChanged(); };

  return (
    <div className="form">
      <StatusMessage status={action.status} />
      <dl className="kv">
        <dt>Available</dt><dd>{inv?.available_quantity ?? "-"}</dd>
        <dt>Reserved (in open orders)</dt><dd>{inv?.reserved_quantity ?? "-"}</dd>
        <dt>Sellable</dt><dd><strong>{inv?.sellable_quantity ?? "-"}</strong> {inv?.is_low_stock && <span className="badge badge-warn">LOW</span>}</dd>
      </dl>
      {canManage && (
        <div className="grid-3">
          <form className="form" onSubmit={(e) => { e.preventDefault(); const d = Number(delta); if (!Number.isInteger(d) || d === 0) return action.setStatus({ type: "error", text: "Enter a whole number other than 0 (negative to remove)." }); action.run(async () => { await adjustStock(variant.id, d, reason, emptyToNull(note)); setDelta(""); setNote(""); done(); }, "Stock adjusted", "Could not adjust stock"); }}>
            <Field label="Add / remove units"><input type="number" step="1" value={delta} onChange={(e) => setDelta(e.target.value)} placeholder="+10 or -2" /></Field>
            <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason">{REASONS.map((r) => <option key={r}>{r}</option>)}</select>
            <input placeholder="Note" value={note} onChange={(e) => setNote(e.target.value)} />
            <button disabled={action.busy}>Adjust</button>
          </form>
          <form className="form" onSubmit={(e) => { e.preventDefault(); const q = Number(exact); if (!Number.isInteger(q) || q < 0) return action.setStatus({ type: "error", text: "Enter a stock count of 0 or more." }); action.run(async () => { await setStock(variant.id, q, "Stock count"); setExact(""); done(); }, "Stock set", "Could not set stock"); }}>
            <Field label="Set exact count" hint="After a physical stock count"><input type="number" min="0" value={exact} onChange={(e) => setExact(e.target.value)} /></Field>
            <button disabled={action.busy || exact === ""}>Set stock</button>
          </form>
          <form className="form" onSubmit={(e) => { e.preventDefault(); const t = Number(alertAt); if (!Number.isInteger(t) || t < 0) return; action.run(async () => { await setThreshold(variant.id, t); done(); }, "Alert level saved", "Could not save alert level"); }}>
            <Field label="Low-stock alert at"><input type="number" min="0" value={alertAt} onChange={(e) => setAlertAt(e.target.value)} /></Field>
            <button disabled={action.busy}>Save alert level</button>
          </form>
        </div>
      )}
      <h4>Movements</h4>
      <DataTable
        rows={movements.data}
        loading={movements.loading}
        error={movements.error}
        empty="No stock movements."
        rowKey={(m) => m.id}
        columns={[
          { key: "delta", header: "Change", align: "right", render: (m) => (m.delta > 0 ? `+${m.delta}` : m.delta) },
          { key: "reason", header: "Reason" },
          { key: "reference", header: "Reference", render: (m) => m.reference ?? "-" },
          { key: "note", header: "Note", render: (m) => m.note ?? "-" },
        ]}
      />
      <Pagination meta={movements.meta} onPageChange={setPage} />
    </div>
  );
}

export default InventoryPanel;
