import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate } from "react-router-dom";
import {
  platformBrands,
  platformCheckDomain,
  platformDomains,
  platformOverview,
  platformSystem,
  platformVerifyDomain,
  reinstateBrand,
  suspendBrand,
} from "../../api/platform";
import { useAuth } from "../../auth/AuthContext";
import ConfirmButton from "../../components/common/ConfirmButton";
import Modal from "../../components/common/Modal";
import Pagination from "../../components/common/Pagination";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { DomainCheck, PlatformBrand, PlatformDomain } from "../../types/platform";
import "./platform.css";

type Tab = "brands" | "domains" | "system";
const TAB_LABELS: Record<Tab, string> = { brands: "Brands", domains: "Domains", system: "System" };

/**
 * The CliQ. operator console: platform totals, brands (suspend / reinstate)
 * and custom domains (DNS check, manual approval). Counts only -- brands'
 * orders and customers are not visible here. Every action is written to the
 * affected brand's activity log.
 */
export default function PlatformConsole() {
  const { merchant, checking } = useAuth();
  const [tab, setTab] = useState<Tab>("brands");

  if (checking) return <div className="state">Checking your session…</div>;
  if (!merchant) return <Navigate to="/signin" replace />;
  if (!merchant.is_platform_admin) return <Navigate to="/brands" replace />;

  return (
    <div className="brands-page platform-page">
      <header className="brands-header">
        <div className="login-wordmark"><span className="brand-name">CliQ.</span><span className="brand-caption">PLATFORM</span></div>
        <div className="brands-account">
          <Link to="/brands">My brands</Link>
          <span className="muted">{merchant.email}</span>
        </div>
      </header>
      <main className="platform-main">
        <h1>Platform</h1>
        <Overview />
        <div className="tabs" role="tablist" aria-label="Platform sections">
          {(["brands", "domains", "system"] as Tab[]).map((t) => (
            <button key={t} type="button" role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
              {TAB_LABELS[t]}
            </button>
          ))}
        </div>
        {tab === "brands" ? <BrandsTab /> : tab === "domains" ? <DomainsTab /> : <SystemTab />}
      </main>
    </div>
  );
}

function Overview() {
  const totals = useApi(() => platformOverview(), []);
  if (totals.error) return <div className="status status-error" role="alert">{totals.error}</div>;
  const d = totals.data;
  const cards: [string, number | undefined][] = [
    ["Brands", d?.brands_total],
    ["Active", d?.brands_active],
    ["Suspended", d?.brands_suspended],
    ["Live stores", d?.stores_published],
    ["Domains to verify", d?.domains_pending],
    ["Merchant accounts", d?.merchant_accounts],
  ];
  return (
    <dl className="platform-totals">
      {cards.map(([label, value]) => (
        <div key={label} className="panel">
          <dt>{label}</dt>
          <dd>{value ?? "…"}</dd>
        </div>
      ))}
    </dl>
  );
}

function BrandsTab() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState({ page: 1, search: "", status: "" });
  const brands = useApi(() => platformBrands({ page: query.page, page_size: 20, search: query.search || undefined, status: query.status || undefined }), [query]);
  const [suspending, setSuspending] = useState<PlatformBrand | null>(null);
  const action = useAction();

  return (
    <section aria-label="Brands">
      <form
        className="platform-filters"
        onSubmit={(e) => { e.preventDefault(); setQuery({ ...query, page: 1, search: search.trim() }); }}
      >
        <input type="search" aria-label="Search brands" placeholder="Search by name or slug" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select aria-label="Status" value={query.status} onChange={(e) => setQuery({ ...query, page: 1, status: e.target.value })}>
          <option value="">All statuses</option>
          <option value="ACTIVE">Active</option>
          <option value="SUSPENDED">Suspended</option>
        </select>
        <button type="submit">Search</button>
      </form>
      <StatusMessage status={action.status} />
      {brands.error && <div className="status status-error" role="alert">{brands.error}</div>}
      {brands.loading && !brands.data && <div className="state">Loading brands…</div>}
      {brands.data?.length === 0 && <div className="state">No brands match.</div>}
      <ul className="platform-list">
        {brands.data?.map((row) => {
          const suspended = row.brand.status !== "ACTIVE";
          return (
            <li key={row.brand.id} className="panel platform-row">
              <div className="platform-row-main">
                <strong>{row.brand.name}</strong>
                <span className="muted">{row.brand.slug} · {row.member_count} member{row.member_count === 1 ? "" : "s"} · since {new Date(row.brand.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</span>
                {row.store && <a href={row.store.url} target="_blank" rel="noreferrer">{row.store.url.replace(/^https?:\/\//, "")} ↗</a>}
                {suspended && row.suspension_reason && <span className="platform-reason">Suspended: {row.suspension_reason}</span>}
              </div>
              <div className="platform-row-badges">
                <span className={`badge ${suspended ? "badge-bad" : "badge-ok"}`}>{suspended ? "Suspended" : "Active"}</span>
                {row.store && <span className={`badge ${row.store.published ? "badge-ok" : "badge-warn"}`}>{row.store.published ? "Live" : "Unpublished"}</span>}
              </div>
              {suspended ? (
                <ConfirmButton
                  className="primary"
                  message={`Reinstate ${row.brand.name}? Its store and team regain access immediately.`}
                  confirmLabel="Reinstate"
                  disabled={action.busy}
                  onConfirm={async () => {
                    if (await action.run(() => reinstateBrand(row.brand.id), `${row.brand.name} reinstated.`, "Could not reinstate")) brands.reload();
                  }}
                >
                  Reinstate
                </ConfirmButton>
              ) : (
                <button type="button" className="danger" onClick={() => setSuspending(row)} disabled={action.busy}>Suspend</button>
              )}
            </li>
          );
        })}
      </ul>
      <Pagination meta={brands.meta} onPageChange={(page) => setQuery({ ...query, page })} />
      {suspending && (
        <SuspendDialog
          brand={suspending}
          onClose={() => setSuspending(null)}
          onDone={() => { setSuspending(null); brands.reload(); }}
        />
      )}
    </section>
  );
}

function SuspendDialog({ brand, onClose, onDone }: { brand: PlatformBrand; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const action = useAction();
  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!reason.trim()) return;
    if (await action.run(() => suspendBrand(brand.brand.id, reason.trim()), null, "Could not suspend")) onDone();
  }
  return (
    <Modal title={`Suspend ${brand.brand.name}`} onClose={onClose}>
      <form className="form" onSubmit={submit}>
        <p>
          Its storefront goes offline and its team loses access at once. Data is kept, and you can reinstate the brand
          at any time. The brand sees this action and your reason in its activity log.
        </p>
        <label className="field">
          <span className="field-label">Reason</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={3} required />
        </label>
        <StatusMessage status={action.status} />
        <div className="platform-dialog-actions">
          <button type="button" onClick={onClose}>Cancel</button>
          <button className="danger" disabled={!reason.trim() || action.busy}>Suspend brand</button>
        </div>
      </form>
    </Modal>
  );
}

function DomainsTab() {
  const [query, setQuery] = useState({ page: 1, status: "pending" });
  const domains = useApi(() => platformDomains({ page: query.page, page_size: 20, status: query.status || undefined }), [query]);

  return (
    <section aria-label="Domains">
      <div className="platform-filters">
        <select aria-label="Domain status" value={query.status} onChange={(e) => setQuery({ page: 1, status: e.target.value })}>
          <option value="pending">Waiting for verification</option>
          <option value="verified">Verified</option>
          <option value="">All</option>
        </select>
      </div>
      {domains.error && <div className="status status-error" role="alert">{domains.error}</div>}
      {domains.loading && !domains.data && <div className="state">Loading domains…</div>}
      {domains.data?.length === 0 && <div className="state">{query.status === "pending" ? "No domains are waiting." : "No domains."}</div>}
      <ul className="platform-list">
        {domains.data?.map((row) => <DomainRow key={row.domain.id} row={row} onChanged={domains.reload} />)}
      </ul>
      <Pagination meta={domains.meta} onPageChange={(page) => setQuery({ ...query, page })} />
    </section>
  );
}

function DomainRow({ row, onChanged }: { row: PlatformDomain; onChanged: () => void }) {
  const action = useAction();
  const [check, setCheck] = useState<DomainCheck | null>(null);
  const verified = !!row.domain.verified_at;
  return (
    <li className="panel platform-row">
      <div className="platform-row-main">
        <strong>{row.domain.domain}</strong>
        <span className="muted">{row.brand_name}{row.store_subdomain ? ` · ${row.store_subdomain}` : ""} · added {new Date(row.domain.created_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</span>
        {check && !check.verified && (
          <span className="platform-reason">
            {check.problem} Expected <code>{check.expected}</code> at <code>{check.record_name}</code>
            {check.found.length > 0 && <> — found <code>{check.found.join(", ")}</code></>}
          </span>
        )}
      </div>
      <div className="platform-row-badges">
        <span className={`badge ${verified ? "badge-ok" : "badge-warn"}`}>{verified ? "Verified" : "Pending"}</span>
      </div>
      {!verified && (
        <div className="platform-row-actions">
          <button
            type="button"
            disabled={action.busy}
            onClick={async () => {
              const result = await action.run(() => platformCheckDomain(row.domain.id), null, "DNS check failed");
              if (!result) return;
              setCheck(result.data);
              if (result.data.verified) {
                action.setStatus({ type: "success", text: `${row.domain.domain} verified by DNS.` });
                onChanged();
              }
            }}
          >
            Check DNS
          </button>
          <ConfirmButton
            className="primary"
            message={`Verify ${row.domain.domain} without a DNS match? Only do this if you have confirmed ownership another way. The brand will see this in its activity log.`}
            confirmLabel="Verify"
            disabled={action.busy}
            onConfirm={async () => {
              if (await action.run(() => platformVerifyDomain(row.domain.id), `${row.domain.domain} verified.`, "Could not verify")) onChanged();
            }}
          >
            Verify manually
          </ConfirmButton>
        </div>
      )}
      <StatusMessage status={action.status} />
    </li>
  );
}

const JOB_STATUS_LABEL: Record<string, string> = { ok: "OK", failed: "Failed", stale: "Not running", never_ran: "Never ran" };

function when(value: string | null): string {
  return value ? new Date(value).toLocaleString() : "—";
}

/** Dependencies, background jobs and which providers still need credentials. */
function SystemTab() {
  const health = useApi(() => platformSystem(), []);
  if (health.loading && !health.data) return <div className="state">Loading…</div>;
  if (health.error) return <div className="status status-error" role="alert">{health.error}</div>;
  const h = health.data;
  if (!h) return null;
  const checks: [string, boolean][] = [
    ["Database", h.database],
    ["Redis", h.redis],
    ["Error reporting", h.error_reporting],
    ["Alerts", h.alerts],
  ];
  return (
    <section aria-label="System" className="platform-system">
      <p className="muted">
        Environment <strong>{h.environment}</strong>{h.release ? <> · release <strong>{h.release}</strong></> : null}
        {" "}<button type="button" className="btn btn-sm" onClick={() => health.reload()}>Refresh</button>
      </p>
      <ul className="platform-checks">
        {checks.map(([label, okay]) => (
          <li key={label} className={okay ? "ok" : "bad"}>{label}: {okay ? "OK" : label === "Database" || label === "Redis" ? "Unavailable" : "Not set up"}</li>
        ))}
      </ul>
      <h2>Background jobs</h2>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Job</th><th>Status</th><th>Last run</th><th>Last success</th><th>Problem</th></tr></thead>
        <tbody>
          {h.jobs.map((j) => (
            <tr key={j.name}>
              <td>{j.name}</td>
              <td><span className={`badge badge-${j.status === "ok" ? "ok" : j.status === "never_ran" ? "warn" : "bad"}`}>{JOB_STATUS_LABEL[j.status]}</span></td>
              <td>{when(j.last_run_at)}</td>
              <td>{when(j.last_ok_at)}</td>
              <td>{j.error ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </table></div>
      <h2>Providers</h2>
      <div className="table-wrap"><table className="table">
        <thead><tr><th>Provider</th><th>Needed for</th><th>Credentials</th></tr></thead>
        <tbody>
          {h.providers.map((p) => (
            <tr key={p.key}>
              <td>{p.name}</td>
              <td>{p.needed_for}</td>
              <td><span className={`badge badge-${p.configured ? "ok" : "warn"}`}>{p.configured ? "Configured" : "Missing"}</span></td>
            </tr>
          ))}
        </tbody>
      </table></div>
    </section>
  );
}
