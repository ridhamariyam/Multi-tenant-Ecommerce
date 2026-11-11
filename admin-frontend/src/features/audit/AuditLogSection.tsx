import { useState } from "react";
import { Link } from "react-router-dom";
import { listAuditLogs } from "../../api/audit";
import { useAuth } from "../../auth/AuthContext";
import { P } from "../../auth/permissions";
import DataTable from "../../components/common/DataTable";
import GuidedControl from "../../components/guidance/GuidedControl";
import Modal from "../../components/common/Modal";
import PageHeader from "../../components/common/PageHeader";
import Pagination from "../../components/common/Pagination";
import { useApi } from "../../hooks/useApi";
import type { AuditLog } from "../../types/user";
import { formatDate } from "../../utils/formatters";
import "./audit.css";

const EMPTY_FILTERS = { entity_type: "", action: "", start_date: "", end_date: "" };
const RECORD_ROUTES: Record<string, { path: string; permission: string }> = {
  order: { path: "/orders", permission: P.ordersView },
  product: { path: "/products", permission: P.catalogueView },
  customer: { path: "/customers", permission: P.customersView },
};
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function actionLabel(action: string) {
  if (action === "auth.login") return "Signed in";
  if (action === "auth.login_failed") return "Sign-in failed";
  return action.replace(/[._]/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

// Who changed what, and when. Recorded by the backend for every admin change.
function AuditLogSection() {
  const { can } = useAuth();
  const [filters, setFilters] = useState(EMPTY_FILTERS);
  const [page, setPage] = useState(1);
  const validRange = !filters.start_date || !filters.end_date || filters.start_date <= filters.end_date;
  const logs = useApi(() => validRange ? listAuditLogs({ ...filters, page }) : Promise.reject(new Error("End date must be on or after start date.")), [filters, page]);
  const [open, setOpen] = useState<AuditLog | null>(null);
  const set = (k: keyof typeof filters) => (e: { target: { value: string } }) => { setFilters({ ...filters, [k]: e.target.value.trim() }); setPage(1); };
  const recordLink = (log: AuditLog) => {
    const route = RECORD_ROUTES[log.entity_type];
    return route && log.entity_id && UUID.test(log.entity_id) && can(route.permission) ? `${route.path}/${log.entity_id}` : null;
  };

  return (
    <div className="record-page audit-page">
      <PageHeader title="Activity log" subtitle="Every change and every admin/staff sign-in (including failed ones), newest first" />
      <div className="filters audit-filters">
        <GuidedControl hint="Show events for one record type, such as order or product." dismissible><input placeholder="Record type (e.g. order, product)" value={filters.entity_type} onChange={set("entity_type")} aria-label="Record type" /></GuidedControl>
        <GuidedControl hint="Match action-code prefixes, such as auth. for sign-ins."><input placeholder="Action starts with…" value={filters.action} onChange={set("action")} aria-label="Action" /></GuidedControl>
        <button type="button" aria-pressed={filters.action === "auth." && filters.entity_type === "session"} onClick={() => { setFilters({ ...filters, entity_type: "session", action: "auth." }); setPage(1); }}>Sign-ins only</button>
        <input type="date" value={filters.start_date} onChange={set("start_date")} aria-label="From" />
        <input type="date" min={filters.start_date || undefined} value={filters.end_date} onChange={set("end_date")} aria-label="To" />
        {Object.values(filters).some(Boolean) && <button type="button" onClick={() => { setFilters(EMPTY_FILTERS); setPage(1); }}>Clear filters</button>}
      </div>
      <div className="panel record-table-panel audit-table-panel">
        <DataTable
          rows={logs.data}
          loading={logs.loading}
          error={logs.error}
          empty="No activity recorded."
          rowKey={(l) => l.id}
          onRowClick={setOpen}
          columns={[
            { key: "created_at", header: "When", render: (l) => formatDate(l.created_at) },
            { key: "actor_name", header: "Who", render: (l) => `${l.actor_name ?? "Unknown account"} (${l.actor_role ?? "-"})` },
            { key: "action", header: "Action", render: (l) => <button type="button" className="audit-action" title={l.action} onClick={(e) => { e.stopPropagation(); setOpen(l); }}>{actionLabel(l.action)}</button> },
            { key: "entity_type", header: "Record", render: (l) => recordLink(l) ? <Link to={recordLink(l)!} onClick={(e) => e.stopPropagation()}>{l.entity_type}</Link> : l.entity_type },
            { key: "summary", header: "Summary", render: (l) => l.summary ?? "-" },
            { key: "ip_address", header: "IP", render: (l) => l.ip_address ?? "-" },
          ]}
        />
        <Pagination meta={logs.meta} onPageChange={setPage} />
      </div>
      {open && (
        <Modal title={`${actionLabel(open.action)} · ${open.entity_type}`} onClose={() => setOpen(null)} wide>
          <dl className="kv">
            <dt>When</dt><dd>{formatDate(open.created_at)}</dd>
            <dt>Who</dt><dd>{open.actor_name ?? "Unknown account"} ({open.actor_role ?? "-"})</dd>
            <dt>Action code</dt><dd><code>{open.action}</code></dd>
            <dt>Record</dt><dd>{open.entity_type}{recordLink(open) && <> · <Link to={recordLink(open)!} onClick={() => setOpen(null)}>Open record</Link></>}</dd>
            <dt>Record ID</dt><dd>{open.entity_id ?? "-"}</dd>
            <dt>IP</dt><dd>{open.ip_address ?? "-"}</dd>
            <dt>Summary</dt><dd>{open.summary ?? "-"}</dd>
          </dl>
          <h4 className="audit-details-heading">Recorded details</h4>
          {open.changes === null ? <p className="muted">No additional details were recorded.</p> : <pre className="code audit-details">{JSON.stringify(open.changes, null, 2)}</pre>}
        </Modal>
      )}
    </div>
  );
}

export default AuditLogSection;
