import { useState } from "react";
import { addDomain, checkDomain, getStore, listDomains, publishStore, removeDomain, updateStore } from "../../api/platform";
import ConfirmButton from "../../components/common/ConfirmButton";
import Field from "../../components/common/Field";
import PageHeader from "../../components/common/PageHeader";
import StatusMessage from "../../components/common/StatusMessage";
import { useAction } from "../../hooks/useAction";
import { useApi } from "../../hooks/useApi";
import type { Store, StoreDomain } from "../../types/platform";
import "./store.css";

const COLOR = /^#[0-9a-fA-F]{6}$/;
const DOMAIN = /^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$/;
const THEMES = [
  { value: "runway", label: "Runway — editorial, image-led" },
  { value: "minimal", label: "Minimal — clean product grid" },
];

/** The open brand's storefront: name, look, address, publishing and custom domains. */
export default function StoreSection() {
  const store = useApi(getStore, []);
  return (
    <div className="store-page">
      <PageHeader title="Store & branding" subtitle="How your storefront looks and where shoppers find it" />
      {store.error && <div className="status status-error" role="alert">{store.error}</div>}
      {!store.data && !store.error && <div className="state">Loading your store…</div>}
      {store.data && <StoreForms key={store.data.id} initial={store.data} />}
      {store.data && <DomainsPanel target={new URL(store.data.url).hostname} />}
    </div>
  );
}

function StoreForms({ initial }: { initial: Store }) {
  const [store, setStore] = useState(initial);
  return (
    <>
      <PublishPanel store={store} onChange={setStore} />
      <BrandingPanel store={store} onChange={setStore} />
    </>
  );
}

function PublishPanel({ store, onChange }: { store: Store; onChange: (s: Store) => void }) {
  const action = useAction();
  const toggle = async (published: boolean) => {
    const saved = await action.run(
      () => publishStore(published),
      published ? "Your store is live." : "Your store is offline. Shoppers now see a “store not available” page.",
      published ? "Could not publish" : "Could not unpublish",
    );
    if (saved?.data) onChange(saved.data);
  };
  return (
    <section className="panel store-panel" aria-labelledby="publish-title">
      <div className="store-publish">
        <div>
          <h3 id="publish-title">
            Storefront <span className={`badge ${store.published ? "badge-ok" : "badge-warn"}`}>{store.published ? "Live" : "Not published"}</span>
          </h3>
          <p className="muted">
            <a href={store.url} target="_blank" rel="noreferrer">{store.url.replace(/^https?:\/\//, "")} ↗</a>
            {store.published_at && store.published && <> · live since {new Date(store.published_at).toLocaleDateString("en-IN", { dateStyle: "medium" })}</>}
          </p>
          {!store.published && <p className="muted">Only you and your team can preview it until it is published.</p>}
        </div>
        {store.published ? (
          <ConfirmButton
            className="danger"
            message="Take the store offline? Shoppers will see a “store not available” page until you publish it again. Orders already placed are not affected."
            confirmLabel="Unpublish"
            onConfirm={() => toggle(false)}
            disabled={action.busy}
          >
            Unpublish
          </ConfirmButton>
        ) : (
          <button type="button" className="primary" onClick={() => toggle(true)} disabled={action.busy}>
            Publish store
          </button>
        )}
      </div>
      <StatusMessage status={action.status} />
    </section>
  );
}

function BrandingPanel({ store, onChange }: { store: Store; onChange: (s: Store) => void }) {
  const [form, setForm] = useState({
    name: store.name,
    subdomain: store.subdomain,
    theme: store.theme,
    logo_url: store.logo_url ?? "",
    favicon_url: store.favicon_url ?? "",
    primary_color: store.primary_color ?? "",
    secondary_color: store.secondary_color ?? "",
  });
  const [errors, setErrors] = useState<Record<string, string>>({});
  const action = useAction();
  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm({ ...form, [key]: e.target.value });

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const local: Record<string, string> = {};
    if (!form.name.trim()) local.name = "Enter the store name.";
    for (const key of ["primary_color", "secondary_color"] as const) {
      if (form[key] && !COLOR.test(form[key])) local[key] = "Use a hex colour like #0D133C.";
    }
    setErrors(local);
    if (Object.keys(local).length) return;
    const saved = await action.run(
      () =>
        updateStore({
          name: form.name.trim(),
          subdomain: form.subdomain.trim(),
          theme: form.theme,
          logo_url: form.logo_url.trim() || null,
          favicon_url: form.favicon_url.trim() || null,
          primary_color: form.primary_color || null,
          secondary_color: form.secondary_color || null,
        }),
      "Saved. The storefront shows the change within a minute.",
      "Could not save",
    );
    if (saved?.data) onChange(saved.data);
  }

  const colour = (key: "primary_color" | "secondary_color", label: string, hint: string) => (
    <Field label={label} hint={hint} error={errors[key]}>
      <span className="store-colour">
        <input type="color" aria-label={`${label} picker`} value={COLOR.test(form[key]) ? form[key] : "#ffffff"} onChange={set(key)} />
        <input value={form[key]} onChange={set(key)} placeholder="#0D133C" maxLength={7} />
      </span>
    </Field>
  );

  return (
    <section className="panel store-panel" aria-labelledby="branding-title">
      <h3 id="branding-title">Branding</h3>
      <form className="form" onSubmit={save} noValidate>
        <div className="form-grid">
          <Field label="Store name" required error={errors.name}>
            <input value={form.name} onChange={set("name")} maxLength={150} />
          </Field>
          <Field label="Store address" hint="Changing it breaks links shoppers saved to the old address.">
            <input value={form.subdomain} onChange={set("subdomain")} maxLength={63} />
          </Field>
          <Field label="Theme">
            <select value={form.theme} onChange={set("theme")}>
              {THEMES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
          {colour("primary_color", "Primary colour", "Header text, buttons and links.")}
          {colour("secondary_color", "Accent colour", "Footer and highlights.")}
          <Field label="Logo URL" hint="An image link (PNG or SVG, transparent background). Leave empty to show the store name." wide>
            <input value={form.logo_url} onChange={set("logo_url")} placeholder="https://…" maxLength={2048} />
          </Field>
          <Field label="Favicon URL" hint="Small square icon shown in the browser tab." wide>
            <input value={form.favicon_url} onChange={set("favicon_url")} placeholder="https://…" maxLength={2048} />
          </Field>
        </div>
        {form.logo_url && (
          <div className="store-logo-preview" style={form.primary_color && COLOR.test(form.primary_color) ? { borderColor: form.primary_color } : undefined}>
            <img src={form.logo_url} alt="Logo preview" />
          </div>
        )}
        <StatusMessage status={action.status} />
        <div><button className="primary" disabled={action.busy}>Save branding</button></div>
      </form>
    </section>
  );
}

function DomainsPanel({ target }: { target: string }) {
  const domains = useApi(listDomains, []);
  const [value, setValue] = useState("");
  const [error, setError] = useState<string | null>(null);
  const action = useAction();

  async function add(e: React.FormEvent) {
    e.preventDefault();
    const domain = value.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/\/.*$/, "").replace(/\.$/, "");
    if (!DOMAIN.test(domain)) {
      setError("Enter a domain like shop.yourbrand.com.");
      return;
    }
    setError(null);
    const added = await action.run(() => addDomain(domain), "Domain added. Follow the steps below to connect it.", "Could not add the domain");
    if (added) {
      setValue("");
      domains.reload();
    }
  }

  return (
    <section className="panel store-panel" aria-labelledby="domains-title">
      <h3 id="domains-title">Custom domains</h3>
      <p className="muted">Use your own address (for example shop.yourbrand.com) as well as your CliQ. address.</p>
      <form className="store-domain-add" onSubmit={add} noValidate>
        <Field label="Domain" error={error}>
          <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="shop.yourbrand.com" maxLength={253} inputMode="url" />
        </Field>
        <button className="primary" disabled={action.busy}>Add domain</button>
      </form>
      <StatusMessage status={action.status} />
      {domains.error && <div className="status status-error" role="alert">{domains.error}</div>}
      {domains.data && domains.data.length === 0 && <p className="muted">No custom domains yet.</p>}
      <ul className="store-domains">
        {domains.data?.map((d) => (
          <DomainRow key={d.id} domain={d} target={target} onChanged={domains.reload} />
        ))}
      </ul>
    </section>
  );
}

function DomainRow({ domain, target, onChanged }: { domain: StoreDomain; target: string; onChanged: () => void }) {
  const action = useAction();
  const verified = !!domain.verified_at;
  return (
    <li className="store-domain">
      <div className="store-domain-head">
        <strong>{domain.domain}</strong>
        <span className={`badge ${verified ? "badge-ok" : "badge-warn"}`}>{verified ? "Connected" : "Waiting for verification"}</span>
        {domain.is_primary && <span className="badge badge-info">Primary</span>}
        <ConfirmButton
          className="danger store-domain-remove"
          message={`Remove ${domain.domain}? Shoppers using it will no longer reach your store.`}
          confirmLabel="Remove"
          disabled={action.busy}
          onConfirm={async () => {
            if (await action.run(() => removeDomain(domain.id), null, "Could not remove")) onChanged();
          }}
        >
          Remove
        </ConfirmButton>
      </div>
      {!verified && (
        <ol className="store-dns">
          <li>
            At your domain provider, add a <strong>CNAME</strong> record for <code>{domain.domain}</code> pointing to{" "}
            <code>{target}</code>.
          </li>
          {domain.verification_record && (
            <li>
              Add a <strong>TXT</strong> record at <code>_cliq-verify.{domain.domain}</code> with the value{" "}
              <code className="store-dns-value">{domain.verification_record}</code>
            </li>
          )}
          <li>
            Then press <strong>Check now</strong>. DNS changes can take up to 48 hours to appear.
          </li>
        </ol>
      )}
      {!verified && (
        <button
          type="button"
          className="store-domain-check"
          disabled={action.busy}
          onClick={async () => {
            const result = await action.run(() => checkDomain(domain.id), null, "Could not check DNS");
            if (!result) return;
            if (result.data.verified) {
              action.setStatus({ type: "success", text: `${domain.domain} is connected.` });
              onChanged();
            } else {
              action.setStatus({ type: "error", text: result.data.problem ?? "Not verified yet." });
            }
          }}
        >
          Check now
        </button>
      )}
      <StatusMessage status={action.status} />
    </li>
  );
}
