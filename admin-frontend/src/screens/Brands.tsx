import { useState } from "react";
import type { FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { listMyBrands, registerBrand } from "../api/platform";
import { useAuth } from "../auth/AuthContext";
import { useApi } from "../hooks/useApi";
import type { BrandMembership } from "../types/platform";
import "./brands.css";

const SUBDOMAIN = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;
const ROLE_LABELS: Record<string, string> = {
  OWNER: "Owner",
  ADMIN: "Admin",
  PRODUCT_MANAGER: "Product manager",
  ORDER_MANAGER: "Order manager",
};

const suggestSubdomain = (name: string) =>
  name.toLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);

/** The merchant's brands: open one, or create a new brand with its store. */
function Brands() {
  const { merchant, checking, openBrand, logout } = useAuth();
  const navigate = useNavigate();
  const welcome = (useLocation().state as { welcome?: boolean } | null)?.welcome;
  const brands = useApi(() => listMyBrands(), [merchant?.id]);
  const [opening, setOpening] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (checking) return <div className="state">Checking your session…</div>;
  if (!merchant) return <Navigate to="/signin" replace />;

  async function open(brandId: string, token?: string) {
    setOpening(brandId);
    setError(null);
    try {
      await openBrand(brandId, token);
      navigate("/", { replace: true });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setOpening(null);
    }
  }

  const list = brands.data ?? [];
  const firstRun = brands.data !== null && list.length === 0;

  return (
    <div className="brands-page">
      <header className="brands-header">
        <div className="login-wordmark"><span className="brand-name">CliQ.</span><span className="brand-caption">LIMITLESS STYLE</span></div>
        <div className="brands-account">
          {merchant.is_platform_admin && <Link to="/platform">Platform admin</Link>}
          <span className="muted">{merchant.name ?? merchant.email}</span>
          <button type="button" onClick={() => logout()}>Sign out</button>
        </div>
      </header>

      <main className="brands-main">
        <h1>{firstRun ? (welcome ? "Welcome to CliQ." : "Create your first brand") : "Your brands"}</h1>
        <p className="muted">
          {firstRun
            ? "A brand gets its own store, products, orders, customers and team. You can add more brands later."
            : "Choose a brand to manage. Each brand's data is kept separate."}
        </p>
        {error && <div className="status status-error" role="alert">{error}</div>}
        {brands.error && <div className="status status-error" role="alert">{brands.error}</div>}
        {brands.loading && !brands.data && <div className="state">Loading your brands…</div>}

        {list.length > 0 && (
          <ul className="brand-cards">
            {list.map((m) => (
              <BrandCard key={m.brand.id} membership={m} busy={opening === m.brand.id} disabled={!!opening} onOpen={() => open(m.brand.id)} />
            ))}
          </ul>
        )}

        {brands.data !== null && <CreateBrand open={firstRun} onCreated={(id, token) => open(id, token)} />}
      </main>
    </div>
  );
}

function BrandCard({ membership, busy, disabled, onOpen }: { membership: BrandMembership; busy: boolean; disabled: boolean; onOpen: () => void }) {
  const { brand, store, role } = membership;
  const suspended = brand.status !== "ACTIVE";
  return (
    <li className="brand-card">
      <div className="brand-card-mark" aria-hidden="true" style={store?.primary_color ? { background: store.primary_color } : undefined}>
        {brand.name.trim().charAt(0).toUpperCase()}
      </div>
      <div className="brand-card-body">
        <strong>{brand.name}</strong>
        <span className="muted">{ROLE_LABELS[role] ?? role}</span>
        {store && (
          <span className="brand-card-store">
            <span className={`badge ${store.published ? "badge-ok" : "badge-warn"}`}>{store.published ? "Live" : "Not published"}</span>
            <a href={store.url} target="_blank" rel="noreferrer">{store.url.replace(/^https?:\/\//, "")}</a>
          </span>
        )}
        {suspended && <span className="badge badge-bad">Suspended</span>}
      </div>
      <button type="button" className="primary" onClick={onOpen} disabled={disabled || suspended}>
        {busy ? "Opening…" : "Manage"}
      </button>
    </li>
  );
}

function CreateBrand({ open, onCreated }: { open: boolean; onCreated: (brandId: string, token: string) => void }) {
  const [expanded, setExpanded] = useState(open);
  const [name, setName] = useState("");
  const [subdomain, setSubdomain] = useState("");
  const [touched, setTouched] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const effectiveSubdomain = touched ? subdomain : suggestSubdomain(name);

  if (!expanded) {
    return (
      <button type="button" className="brand-add" onClick={() => setExpanded(true)}>
        + Create another brand
      </button>
    );
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const local: Record<string, string> = {};
    if (!name.trim()) local.name = "Enter the brand's name.";
    if (effectiveSubdomain && !SUBDOMAIN.test(effectiveSubdomain)) {
      local.subdomain = "Use lowercase letters, numbers and hyphens (not at the start or end).";
    }
    setErrors(local);
    if (Object.keys(local).length) return;
    setBusy(true);
    setError(null);
    try {
      const created = await registerBrand({ name: name.trim(), ...(effectiveSubdomain.length >= 2 ? { subdomain: effectiveSubdomain } : {}) });
      onCreated(created.data.brand.id, created.data.token.access_token);
    } catch (e) {
      if (e instanceof ApiError && e.details.length) {
        setErrors(Object.fromEntries(e.details.filter((d) => d.field).map((d) => [String(d.field).split(".").pop(), d.message])));
      }
      setError(e instanceof Error ? e.message : String(e));
      setBusy(false);
    }
  }

  return (
    <form className="panel form brand-create" onSubmit={submit} noValidate>
      <h2>New brand</h2>
      <label className="field">
        <span className="field-label">Brand name</span>
        <input value={name} onChange={(e) => setName(e.target.value)} maxLength={150} aria-invalid={!!errors.name} autoFocus={open} />
        {errors.name && <span className="field-error" role="alert">{errors.name}</span>}
      </label>
      <div className="field">
        <label className="field-label" htmlFor="brand-subdomain">Store address</label>
        <span className="brand-subdomain">
          <input
            id="brand-subdomain"
            value={effectiveSubdomain}
            onChange={(e) => { setTouched(true); setSubdomain(e.target.value.toLowerCase()); }}
            maxLength={63}
            aria-invalid={!!errors.subdomain}
            aria-describedby="subdomain-hint"
          />
          <span className="muted" aria-hidden="true">.{process.env.NEXT_PUBLIC_PLATFORM_ROOT_DOMAIN || "localhost"}</span>
        </span>
        <span id="subdomain-hint" className="field-hint">You can connect your own domain later.</span>
        {errors.subdomain && <span className="field-error" role="alert">{errors.subdomain}</span>}
      </div>
      {error && <div className="status status-error" role="alert">{error}</div>}
      <div className="brand-create-actions">
        <button className="primary" type="submit" disabled={busy}>{busy ? "Creating…" : "Create brand"}</button>
        {!open && <button type="button" onClick={() => setExpanded(false)} disabled={busy}>Cancel</button>}
      </div>
    </form>
  );
}

export default Brands;
